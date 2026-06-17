"""
src/classes/missions.py
─────────────────────────
SÉCURITÉ : Mission.execute() n'écrit plus jamais le résultat en clair
sur disque local. Le résultat est chiffré en mémoire avec la clé du
user qui a déclenché la mission, puis envoyé à l'API via PUT.

Cela nécessite que Mission reçoive la clé et le token du user courant
au moment de sa création (transmis depuis la requête HTTP authentifiée
qui a déclenché /run/<workflow_id>) — jamais relus depuis un cookie ou
un stockage côté serveur après coup.
"""

from datetime import datetime
import json
import threading

import src.mission_progress as progress_store
from src.WebUI.crypto_bridge import encrypt_and_put_json_with_key


class MissionEncoder(json.JSONEncoder):
    def default(self, obj):  # type: ignore
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        if hasattr(obj, '__str__'):
            return str(obj)
        return super().default(obj)


class Mission:

    def __init__(self, name, workflow, owner_id: str, owner_key: str, api_base: str, api_token: str):
        """
        owner_id  : id du user qui lance la mission (devient owner_id du fichier)
        owner_key : clé AES-256 b64url du owner, utilisée pour chiffrer le résultat
        api_base  : URL de l'API (ex: http://localhost:5001)
        api_token : JWT du owner, pour authentifier le PUT vers l'API
        """
        self.id             = "#MSN-" + str(abs(hash(name + datetime.now().isoformat())))[:8]
        self.name           = name
        self.workflow       = workflow
        self.status         = "pending"
        self.result         = None
        self.date_created   = datetime.now()
        self.date_completed = None

        self._owner_id  = owner_id
        self._owner_key = owner_key
        self._api_base  = api_base
        self._api_token = api_token

    def execute(self, inputs):
        self.status = "running"

        step_ids = [
            (step.get("id"), step.get("module"))
            for step in self.workflow.wf.get("steps", [])
        ]
        progress = progress_store.register(self.id, step_ids)
        self.workflow.progress = progress

        try:
            self.result = self.workflow.run(inputs)
            self.status = self.workflow.status
        except Exception as e:
            self.result = str(e)
            self.status = "failed"
        finally:
            self.date_completed = datetime.now()
            progress.finish_mission(self.status)

            data = {
                "id":             self.id,
                "name":           self.name,
                "workflow":       self.workflow.id,
                "status":         self.status,
                "inputs":         inputs,
                "result":         self.result,
                "date_created":   self.date_created.isoformat(),
                "date_completed": self.date_completed.isoformat(),
            }
            # Sérialise via MissionEncoder puis ré-ouvre en dict simple,
            # pour garantir que tout ce qu'on chiffre est JSON-compatible.
            serializable = json.loads(json.dumps(data, ensure_ascii=False, cls=MissionEncoder))

            mission_folder_name = f"{self.date_created.strftime('%Y-%m-%d_%H-%M-%S')}_{self.id.lstrip('#')}"
            filename = f"{self.id.lstrip('#')}.json"

            try:
                encrypt_and_put_json_with_key(
                    api_base=self._api_base,
                    token=self._api_token,
                    path=f"/files/missions/{mission_folder_name}/{filename}",
                    data=serializable,
                    original_name=filename,
                    b64_key=self._owner_key,
                )
            except Exception as e:
                print(f"[Mission] Échec de la sauvegarde chiffrée du résultat : {e}")

            def _cleanup():
                import time; time.sleep(300)
                progress_store.unregister(self.id)
            threading.Thread(target=_cleanup, daemon=True).start()