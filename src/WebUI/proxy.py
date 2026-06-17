"""
src/WebUI/proxy.py
──────────────────
Proxy léger entre le WebUI et l'API de fichiers chiffrés.

Le WebUI ne lit/écrit JAMAIS data/ directement, et ne déchiffre jamais.
Il relaie le JWT (depuis le cookie HttpOnly) vers l'API, qui vérifie les
permissions et retourne/stocke le payload chiffré tel quel.

Routes :
  GET  /proxy/files/missions
  GET  /proxy/files/missions/<name>
  GET  /proxy/files/missions/<name>/<file>
  PUT  /proxy/files/missions/<name>/<file>      ← payload déjà chiffré (JS)

  GET  /proxy/files/reports
  GET  /proxy/files/reports/<file>
  PUT  /proxy/files/reports/<file>

  GET  /proxy/files/workflows
  GET  /proxy/files/workflows/<file>
  PUT  /proxy/files/workflows/<file>
"""

import requests
from flask import Blueprint, jsonify, g, request

from src.WebUI.auth import login_required, API_BASE

proxy_bp = Blueprint("proxy", __name__, url_prefix="/proxy")


def _api_get(path: str, token: str):
    try:
        resp = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return resp.json(), resp.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "API inaccessible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def _api_put(path: str, token: str, body: dict):
    """
    Transmet un payload déjà chiffré côté client vers l'API.
    Le WebUI ne touche jamais au contenu — simple relais.
    """
    try:
        resp = requests.put(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=10,
        )
        return resp.json(), resp.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "API inaccessible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


def _api_delete(path: str, token: str):
    try:
        resp = requests.delete(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return resp.json(), resp.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "API inaccessible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


# ─── Missions ─────────────────────────────────────────────────────────────────

@proxy_bp.route("/files/missions")
@login_required
def proxy_list_missions():
    data, status = _api_get("/files/missions", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/missions/<mission_name>")
@login_required
def proxy_list_mission_files(mission_name: str):
    data, status = _api_get(f"/files/missions/{mission_name}", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/missions/<mission_name>/<filename>", methods=["GET"])
@login_required
def proxy_get_mission_file(mission_name: str, filename: str):
    data, status = _api_get(f"/files/missions/{mission_name}/{filename}", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/missions/<mission_name>/<filename>", methods=["PUT"])
@login_required
def proxy_put_mission_file(mission_name: str, filename: str):
    body = request.get_json(silent=True) or {}
    data, status = _api_put(f"/files/missions/{mission_name}/{filename}", g.token, body)
    return jsonify(data), status


# ─── Reports ──────────────────────────────────────────────────────────────────

@proxy_bp.route("/files/reports")
@login_required
def proxy_list_reports():
    data, status = _api_get("/files/reports", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/reports/<filename>", methods=["GET"])
@login_required
def proxy_get_report(filename: str):
    data, status = _api_get(f"/files/reports/{filename}", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/reports/<filename>", methods=["PUT"])
@login_required
def proxy_put_report(filename: str):
    body = request.get_json(silent=True) or {}
    data, status = _api_put(f"/files/reports/{filename}", g.token, body)
    return jsonify(data), status


# ─── Workflows ────────────────────────────────────────────────────────────────

@proxy_bp.route("/files/workflows")
@login_required
def proxy_list_workflows():
    data, status = _api_get("/files/workflows", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/workflows/<filename>", methods=["GET"])
@login_required
def proxy_get_workflow(filename: str):
    data, status = _api_get(f"/files/workflows/{filename}", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/workflows/<filename>", methods=["PUT"])
@login_required
def proxy_put_workflow(filename: str):
    body = request.get_json(silent=True) or {}
    data, status = _api_put(f"/files/workflows/{filename}", g.token, body)
    return jsonify(data), status


@proxy_bp.route("/files/workflows/<filename>", methods=["DELETE"])
@login_required
def proxy_delete_workflow(filename: str):
    data, status = _api_delete(f"/files/workflows/{filename}", g.token)
    return jsonify(data), status


@proxy_bp.route("/files/reports/<filename>", methods=["DELETE"])
@login_required
def proxy_delete_report(filename: str):
    data, status = _api_delete(f"/files/reports/{filename}", g.token)
    return jsonify(data), status


# ─── Erreurs ──────────────────────────────────────────────────────────────────

@proxy_bp.errorhandler(401)
@proxy_bp.errorhandler(403)
@proxy_bp.errorhandler(404)
@proxy_bp.errorhandler(503)
def handle_error(e):
    return jsonify({"error": e.description}), e.code