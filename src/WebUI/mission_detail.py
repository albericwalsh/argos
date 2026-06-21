"""
mission_detail.py — WebUI blueprint
SÉCURITÉ : ne lit plus jamais data/missions/ en clair sur disque.

Routes :
  GET  /missions/<mission_id>          → page de détail (HTML, squelette)
  GET  /missions/<mission_id>/stream   → SSE stream temps réel (missions en cours, en mémoire)
  GET  /missions/<mission_id>/data     → snapshot JSON, déchiffré via l'API si besoin

Pour les missions EN COURS (encore en mémoire process via mission_progress),
le comportement est inchangé : le stream SSE fonctionne directement.

Pour les missions TERMINÉES dont le résultat est sur disque (chiffré),
/data accepte un paramètre ?folder=<mission_folder> pour savoir où aller
chercher le fichier via l'API. Sans ce paramètre, le serveur tente de
deviner le dossier en listant /files/missions et en cherchant un fichier
dont le contenu déchiffré correspond à l'id demandé — plus lent mais
fonctionne même si le frontend n'a pas transmis le dossier exact.
"""

import json
from flask import Blueprint, render_template, Response, jsonify, abort, request, g

from src.WebUI.auth import login_required, API_BASE
import src.mission_progress as progress_store

bp = Blueprint("mission_detail", __name__)


def _find_mission_via_api(mission_id: str, folder_hint: str | None = None) -> dict | None:
    """
    Récupère et déchiffre une mission terminée via l'API.

    Si folder_hint est fourni, va directement chercher dedans (rapide).
    Sinon, liste tous les dossiers de missions visibles par le user
    courant et cherche celui qui contient un fichier dont l'id déchiffré
    correspond à mission_id (plus lent, mais robuste).
    """
    from src.WebUI.crypto_bridge import fetch_and_decrypt_json
    import requests

    clean_id = mission_id.lstrip("#")

    if folder_hint:
        try:
            resp = requests.get(
                f"{API_BASE}/files/missions/{folder_hint}",
                headers={"Authorization": f"Bearer {g.token}"},
                timeout=10,
            )
            resp.raise_for_status()
            files = resp.json()
        except Exception:
            files = []

        for f in files:
            try:
                data = fetch_and_decrypt_json(API_BASE, g.token, f"/files/missions/{folder_hint}/{f['name']}")
                if data.get("id", "").lstrip("#") == clean_id:
                    return data
            except Exception:
                continue
        # folder_hint fourni mais rien trouvé dedans : on retombe sur la
        # recherche globale ci-dessous plutôt que d'abandonner.

    try:
        resp = requests.get(
            f"{API_BASE}/files/missions",
            headers={"Authorization": f"Bearer {g.token}"},
            timeout=10,
        )
        resp.raise_for_status()
        missions_map = resp.json()  # { folder_name: [files...] }
    except Exception as e:
        print(f"[mission_detail] Impossible de lister les missions : {e}")
        return None

    for folder_name, files in missions_map.items():
        for f in files:
            try:
                data = fetch_and_decrypt_json(API_BASE, g.token, f"/files/missions/{folder_name}/{f['name']}")
                if data.get("id", "").lstrip("#") == clean_id:
                    return data
            except Exception:
                continue

    return None


@bp.route("/missions/<mission_id>")
@login_required
def mission_detail(mission_id: str):
    clean_id = mission_id.lstrip("#")
    full_id  = "#" + clean_id
    return render_template("mission_detail.html", mission_id=full_id)


@bp.route("/missions/<mission_id>/stream")
@login_required
def mission_stream(mission_id: str):
    """
    SSE — uniquement pertinent pour une mission EN COURS, encore suivie
    en mémoire (mission_progress). Pour une mission terminée/historique,
    le frontend doit utiliser /data directement (le stream renvoie
    immédiatement un événement not_found dans ce cas).
    """
    full_id = "#" + mission_id.lstrip("#")
    prog = progress_store.get(full_id)
    if prog is None:
        return Response(
            f"event: not_found\ndata: {json.dumps({'mission_id': full_id})}\n\n",
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def generate():
        yield from prog.events()

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/missions/<mission_id>/data")
@login_required
def mission_data(mission_id: str):
    """
    Retourne le JSON complet de la mission.

    1. Cherche en mémoire (mission_progress) si encore en cours/récente.
    2. Sinon, déchiffre via l'API (historique persistant).

    Paramètre optionnel ?folder=<mission_folder> pour accélérer la
    recherche si le frontend le connaît déjà (cas: navigation depuis
    missions.html qui a accès à mission._mission_folder).
    """
    full_id     = "#" + mission_id.lstrip("#")
    folder_hint = request.args.get("folder")

    prog = progress_store.get(full_id)
    if prog:
        return jsonify(prog.snapshot())

    data = _find_mission_via_api(full_id, folder_hint=folder_hint)
    if data is None:
        abort(404, description=f"Mission {full_id} introuvable ou inaccessible")

    result    = data.get("result", {}) or {}
    step_keys = [k for k in result if k != "inputs"]

    steps = []
    for sid in step_keys:
        step_result = result[sid]
        steps.append({
            "id":       sid,
            "module":   sid,
            "status":   "failed" if step_result.get("error") else "completed",
            "logs":     [],
            "started":  None,
            "finished": data.get("date_completed"),
            "error":    step_result.get("error"),
        })

    return jsonify({
        "mission_id":     data.get("id"),
        "mission_name":   data.get("name"),
        "workflow":       data.get("workflow"),
        "status":         data.get("status"),
        "inputs":         data.get("inputs", {}),
        "percent":        100,
        "current_step":   len(steps),
        "steps":          steps,
        "date_created":   data.get("date_created"),
        "date_completed": data.get("date_completed"),
    })