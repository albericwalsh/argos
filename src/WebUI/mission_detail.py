"""
mission_detail.py — WebUI blueprint
Routes :
  GET  /missions/<mission_id>          → page de détail (HTML)
  GET  /missions/<mission_id>/stream   → SSE stream temps réel
  GET  /missions/<mission_id>/data     → snapshot JSON (missions terminées)
"""

import os
import json
from datetime import datetime
from flask import Blueprint, render_template, Response, jsonify, abort

from src.variables import APP_DIR
import src.mission_progress as progress_store

bp = Blueprint("mission_detail", __name__)


def _load_mission_file(mission_id: str) -> dict | None:
    """Cherche et charge le JSON de mission depuis data/missions/."""
    missions_dir = os.path.join(APP_DIR, "data", "missions")
    clean_id = mission_id.lstrip("#")
    for folder in os.listdir(missions_dir):
        if clean_id in folder or mission_id in folder:
            json_path = os.path.join(missions_dir, folder, f"#{clean_id}.json")
            if not os.path.exists(json_path):
                # Cherche n'importe quel .json dans le dossier
                for f in os.listdir(os.path.join(missions_dir, folder)):
                    if f.endswith(".json"):
                        json_path = os.path.join(missions_dir, folder, f)
                        break
            if os.path.exists(json_path):
                with open(json_path, encoding="utf-8") as f:
                    return json.load(f)
    return None


@bp.route("/missions/<mission_id>")
def mission_detail(mission_id: str):
    # Normalise l'ID : le # est un fragment URL, jamais transmis au serveur
    # On accepte "MSN-xxxxxxxx" et on reconstitue "#MSN-xxxxxxxx" en interne
    clean_id = mission_id.lstrip("#")
    full_id  = "#" + clean_id
    return render_template("mission_detail.html", mission_id=full_id)


@bp.route("/missions/<mission_id>/stream")
def mission_stream(mission_id: str):
    mission_id = "#" + mission_id.lstrip("#")
    """
    SSE endpoint — streame les événements de progression en temps réel.
    Si la mission est déjà terminée, retourne un snapshot immédiat via /data.
    """
    prog = progress_store.get(mission_id)
    if prog is None:
        # Mission terminée ou inconnue — le frontend bascule sur /data
        return Response(
            f"event: not_found\ndata: {json.dumps({'mission_id': mission_id})}\n\n",
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
def mission_data(mission_id: str):
    mission_id = "#" + mission_id.lstrip("#")
    """Retourne le JSON complet de la mission (pour les missions terminées)."""
    # Cherche d'abord en mémoire (mission très récente)
    prog = progress_store.get(mission_id)
    if prog:
        return jsonify(prog.snapshot())

    # Sinon charge depuis le disque
    data = _load_mission_file(mission_id)
    if data is None:
        abort(404)

    # Reconstruit un snapshot compatible depuis le JSON sauvegardé
    result = data.get("result", {}) or {}
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
        "mission_id":   data.get("id"),
        "mission_name": data.get("name"),
        "workflow":     data.get("workflow"),
        "status":       data.get("status"),
        "inputs":       data.get("inputs", {}),
        "percent":      100,
        "current_step": len(steps),
        "steps":        steps,
        "date_created":   data.get("date_created"),
        "date_completed": data.get("date_completed"),
    })