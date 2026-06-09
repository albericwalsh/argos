"""
src/WebUI/reports.py
Argos — Routes pour le module Reports.
S'enregistre directement sur l'instance Flask `app` (pas de Blueprint).

Usage dans app.py :
    from src.WebUI.reports import register_reports_routes, REPORTS_DIR
    register_reports_routes(app)
"""

import os
from datetime import datetime
from flask import request, jsonify, send_from_directory, abort, render_template

from src.core.report import generate_report, list_reports
from src.variables import APP_DIR, MISSIONS_REGISTERY

# Dossier de stockage des rapports
REPORTS_DIR = os.path.join(APP_DIR, "data", "reports")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_missions():
    """
    Retourne MISSIONS_REGISTERY sous forme de dict {id: mission_obj}.
    Compatible avec le fait que MISSIONS_REGISTERY est une liste.
    """
    return {m.id: m for m in MISSIONS_REGISTERY}


def _mission_to_dict(m) -> dict:
    """
    Sérialise un objet Mission en dict plat pour le report engine.
    Gère les dates (datetime ou str) et le workflow (objet ou str).
    """
    def _iso(val):
        if val is None:
            return ""
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    def _workflow_id(val):
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        return getattr(val, "id", str(val))

    return {
        "id":             getattr(m, "id",             ""),
        "name":           getattr(m, "name",           ""),
        "workflow":       _workflow_id(getattr(m, "workflow", "")),
        "status":         getattr(m, "status",         ""),
        "inputs":         getattr(m, "inputs",         {}) or {},
        "result":         getattr(m, "result",         {}) or {},
        "date_created":   _iso(getattr(m, "date_created",   None)),
        "date_completed": _iso(getattr(m, "date_completed", None)),
    }


def _completed_missions_from_files() -> list[dict]:
    """
    Charge les missions complétées depuis data/missions/ (historique fichiers).
    Retourne une liste de dicts bruts (déjà sérialisés).
    """
    from src.utils import open_file
    missions_dir = os.path.join(APP_DIR, "data", "missions")
    results = []
    if not os.path.exists(missions_dir):
        return results
    for folder in sorted(os.listdir(missions_dir), reverse=True):
        folder_path = os.path.join(missions_dir, folder)
        if not os.path.isdir(folder_path):
            continue
        for file in os.listdir(folder_path):
            if file.endswith(".json"):
                data = open_file(os.path.join(folder_path, file))
                if isinstance(data, dict) and data.get("status") == "completed":
                    results.append(data)
    return results


# ── Enregistrement des routes ─────────────────────────────────────────────────

def register_reports_routes(app):
    """Enregistre toutes les routes /reports/* sur l'instance Flask."""

    # ── Page principale ───────────────────────────────────────────────────────
    @app.route("/reports")
    def reports_page():
        reports = list_reports(REPORTS_DIR)

        # Missions live complétées (en mémoire)
        live_completed = [
            _mission_to_dict(m)
            for m in MISSIONS_REGISTERY
            if getattr(m, "status", None) == "completed"
        ]
        live_ids = {m["id"] for m in live_completed}

        # Missions complétées depuis les fichiers (évite doublons)
        file_completed = [
            m for m in _completed_missions_from_files()
            if m.get("id") not in live_ids
        ]

        # On passe des dicts à Jinja (pas d'objets Mission)
        completed = live_completed + file_completed

        from src.variables import (
            MODULES_REGISTERY, WORKFLOWS_REGISTERY,
            WEB_SERVER_HOST, WEB_SERVER_PORT,
            APP_NAME, APP_VERSION, APP_DESCRIPTION,
            APP_AUTHOR, APP_LICENSE, APP_REPOSITORY,
        )
        variables = {
            "WEB_SERVER_HOST": WEB_SERVER_HOST,
            "WEB_SERVER_PORT": WEB_SERVER_PORT,
            "APP_NAME": APP_NAME,
            "APP_VERSION": APP_VERSION,
            "APP_DESCRIPTION": APP_DESCRIPTION,
            "APP_AUTHOR": APP_AUTHOR,
            "APP_LICENSE": APP_LICENSE,
            "APP_REPOSITORY": APP_REPOSITORY,
            "MODULES": MODULES_REGISTERY,
            "WORKFLOWS": WORKFLOWS_REGISTERY,
        }
        return render_template(
            "reports.html",
            reports=reports,
            missions=completed,
            **variables
        )

    # ── Génération ────────────────────────────────────────────────────────────
    @app.route("/reports/generate", methods=["POST"])
    def reports_generate():
        """
        POST /reports/generate
        Body JSON : { "mission_id": "#MSN-XXXXXXXX" }
        """
        data       = request.get_json(force=True) or {}
        mission_id = data.get("mission_id", "").strip()
        if not mission_id:
            abort(400, description="mission_id manquant")

        # 1. Cherche en mémoire (objets Mission)
        mission_obj = next(
            (m for m in MISSIONS_REGISTERY if m.id == mission_id), None
        )
        if mission_obj:
            mission_dict = _mission_to_dict(mission_obj)
        else:
            # 2. Cherche dans les fichiers
            file_missions = _completed_missions_from_files()
            mission_dict = next(
                (m for m in file_missions if m.get("id") == mission_id), None
            )
            if not mission_dict:
                abort(404, description=f"Mission {mission_id} introuvable")

        info    = generate_report(mission_dict, REPORTS_DIR)
        reports = list_reports(REPORTS_DIR)
        report  = next((r for r in reports if r["id"] == info["id"]), None)
        return jsonify({"ok": True, "report": report})

    # ── Aperçu HTML ───────────────────────────────────────────────────────────
    @app.route("/reports/preview/<report_id>")
    def reports_preview(report_id):
        safe_id = os.path.basename(report_id)
        if not os.path.exists(os.path.join(REPORTS_DIR, f"{safe_id}.html")):
            abort(404)
        return send_from_directory(
            os.path.abspath(REPORTS_DIR),
            f"{safe_id}.html",
            mimetype="text/html",
        )

    # ── Téléchargement PDF ────────────────────────────────────────────────────
    @app.route("/reports/download/<report_id>")
    def reports_download(report_id):
        safe_id = os.path.basename(report_id)
        if not os.path.exists(os.path.join(REPORTS_DIR, f"{safe_id}.pdf")):
            abort(404)
        return send_from_directory(
            os.path.abspath(REPORTS_DIR),
            f"{safe_id}.pdf",
            as_attachment=True,
            download_name=f"argos-report-{safe_id}.pdf",
        )

    # ── Suppression ───────────────────────────────────────────────────────────
    @app.route("/reports/delete/<report_id>", methods=["DELETE"])
    def reports_delete(report_id):
        safe_id = os.path.basename(report_id)
        for ext in ("html", "pdf"):
            p = os.path.join(REPORTS_DIR, f"{safe_id}.{ext}")
            if os.path.exists(p):
                os.remove(p)
        return jsonify({"ok": True})