from datetime import datetime
import os
import json
import threading

from src.utils import create_file
from src.variables import APP_DIR
import src.mission_progress as progress_store


class MissionEncoder(json.JSONEncoder):
    def default(self, obj):  # type: ignore
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        if hasattr(obj, '__str__'):
            return str(obj)
        return super().default(obj)


class Mission:

    def __init__(self, name, workflow):
        self.id             = "#MSN-" + str(abs(hash(name + datetime.now().isoformat())))[:8]
        self.name           = name
        self.workflow       = workflow
        self.status         = "pending"
        self.result         = None
        self.date_created   = datetime.now()
        self.date_completed = None

    def execute(self, inputs):
        self.status = "running"

        # ── Enregistre le tracker de progression ────────────────────────────
        step_ids = [
            (step.get("id"), step.get("module"))
            for step in self.workflow.wf.get("steps", [])
        ]
        progress = progress_store.register(self.id, step_ids)

        # Injecte le tracker dans le workflow pour que run() l'utilise
        self.workflow.progress = progress

        try:
            self.result = self.workflow.run(inputs)
            self.status = self.workflow.status
        except Exception as e:
            self.result = str(e)
            self.status = "failed"
        finally:
            self.date_completed = datetime.now()

            # Signale la fin au stream SSE
            progress.finish_mission(self.status)

            folder_name = f"{self.date_created.strftime('%Y-%m-%d_%H-%M-%S')}_{self.id}"
            folder_path = os.path.join(APP_DIR, f"data/missions/{folder_name}")
            os.makedirs(folder_path, exist_ok=True)
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
            create_file(
                os.path.join(folder_path, f"{self.id}.json"),
                json.dumps(data, indent=2, ensure_ascii=False, cls=MissionEncoder)
            )

            # Garde le tracker en mémoire 5 min après la fin (pour les clients lents)
            def _cleanup():
                import time; time.sleep(300)
                progress_store.unregister(self.id)
            threading.Thread(target=_cleanup, daemon=True).start()