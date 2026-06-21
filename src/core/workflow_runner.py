"""
src/core/workflow_runner.py
────────────────────────────
SÉCURITÉ : ce module ne charge plus jamais de workflows au démarrage
du process (il n'y a alors aucun utilisateur authentifié, donc aucune
clé disponible pour déchiffrer quoi que ce soit).

Les workflows sont désormais chargés PAR SESSION, après le login d'un
utilisateur, via load_workflows_for_user(). Le WebUI appelle cette
fonction juste après avoir posé les cookies d'authentification.

WORKFLOWS_REGISTERY reste une liste globale par compatibilité avec le
reste du code (Workflow, Mission, etc.) mais son contenu dépend
désormais du DERNIER utilisateur qui s'est connecté dans ce process —
ce qui n'est correct que pour un déploiement mono-utilisateur local
(ex: CLI / outil de poste de travail). Pour un usage multi-utilisateur
concurrent réel, il faudrait remplacer ce registre global par un
registre scoppé à la session HTTP (voir note en fin de fichier).
"""

import requests

from src.classes.workflows import Workflow
from src.variables import WORKFLOWS_REGISTERY


def init_worflow_registery():
    """
    Ancienne fonction de démarrage — désormais un no-op volontaire.
    Conservée pour ne pas casser les imports existants dans main.py,
    mais ne lit plus jamais data/workflows en clair au boot.
    """
    WORKFLOWS_REGISTERY.clear()
    print("[workflow_runner] Registre des workflows vide au démarrage "
          "— chargement différé jusqu'au login d'un utilisateur.")


def load_workflows_for_user(api_base: str, token: str) -> list[Workflow]:
    """
    Appelé par le WebUI juste après un login réussi.
    Récupère et déchiffre (côté serveur WebUI, avec la clé du user
    fraîchement connecté, transmise par ailleurs) la liste des workflows
    auxquels ce user a accès, et reconstruit WORKFLOWS_REGISTERY.

    NOTE : cette fonction a besoin de la clé en clair pour déchiffrer
    côté Python (nécessaire pour peupler les objets Workflow utilisés
    par /run/<id> et le moteur d'exécution). Elle ne doit être appelée
    que dans le contexte d'une requête authentifiée, juste après le
    login, avec la clé reçue depuis la réponse de /auth/login — jamais
    stockée ni journalisée au-delà de cet appel.
    """
    from src.WebUI.crypto_bridge import fetch_and_decrypt_json

    WORKFLOWS_REGISTERY.clear()

    try:
        resp = requests.get(
            f"{api_base}/files/workflows",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json()
    except Exception as e:
        print(f"[workflow_runner] Impossible de lister les workflows : {e}")
        return WORKFLOWS_REGISTERY

    for f in files:
        try:
            wf_dict = fetch_and_decrypt_json(api_base, token, f"/files/workflows/{f['name']}")
            wf = Workflow.from_dict(wf_dict, source_name=f['name'])
            WORKFLOWS_REGISTERY.append(wf)
        except Exception as e:
            print(f"[workflow_runner] Échec chargement {f.get('name')} : {e}")

    print(f"[workflow_runner] {len(WORKFLOWS_REGISTERY)} workflow(s) chargé(s) pour la session.")
    return WORKFLOWS_REGISTERY


def upsert_workflow_in_registry(wf_dict: dict, source_name: str | None = None) -> Workflow:
    """
    Ajoute ou met à jour un workflow dans WORKFLOWS_REGISTERY immédiatement
    après sa création/modification via le builder, sans attendre une
    reconnexion. Appelé juste après un PUT réussi vers l'API (le workflow
    existe déjà en clair en mémoire côté navigateur à ce moment-là — pas
    besoin de re-déchiffrer, le dict est transmis directement par
    l'appelant qui vient de le construire/recevoir).

    Si un workflow avec le même id existe déjà dans le registre, il est
    remplacé (édition). Sinon, il est ajouté (création).
    """
    new_wf = Workflow.from_dict(wf_dict, source_name=source_name)

    existing_idx = next(
        (i for i, w in enumerate(WORKFLOWS_REGISTERY) if w.id == new_wf.id),
        None,
    )
    if existing_idx is not None:
        WORKFLOWS_REGISTERY[existing_idx] = new_wf
        print(f"[workflow_runner] Workflow '{new_wf.id}' mis à jour dans le registre.")
    else:
        WORKFLOWS_REGISTERY.append(new_wf)
        print(f"[workflow_runner] Workflow '{new_wf.id}' ajouté au registre.")

    return new_wf


def remove_workflow_from_registry(workflow_id: str):
    """Retire un workflow du registre (utilisé lors d'une suppression)."""
    idx = next((i for i, w in enumerate(WORKFLOWS_REGISTERY) if w.id == workflow_id), None)
    if idx is not None:
        WORKFLOWS_REGISTERY.pop(idx)
        print(f"[workflow_runner] Workflow '{workflow_id}' retiré du registre.")


# ══════════════════════════════════════════════════════════════════════════════
# NOTE D'ARCHITECTURE — MULTI-UTILISATEUR CONCURRENT
# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOWS_REGISTERY et MISSIONS_REGISTERY sont des listes Python globales
# au process. Si deux utilisateurs différents se connectent EN MÊME TEMPS
# sur la même instance WebUI (un seul process Flask), le second login
# écrasera le registre du premier (load_workflows_for_user vide la liste
# avant de la repeupler). Pour ce projet en l'état (poste de travail local,
# usage mono-session), ce n'est pas un problème. Si un déploiement
# multi-utilisateur concurrent est prévu, il faudra remplacer ces listes
# globales par un cache scoppé par session (ex: dict {session_id: [...]},
# ou stockage dans flask.session / un store Redis), avec une clé d'accès
# liée au cookie de chaque utilisateur plutôt qu'à l'état global du process.