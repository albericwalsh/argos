"""
src/WebUI/account.py
─────────────────────
Page /account — gestion du profil personnel, accessible à tout user
connecté (changement de mot de passe, nom d'affichage, email).

Distinct de /admin/users : ici un user ne peut agir que sur SON propre
compte (l'API vérifie via le JWT, pas via un id transmis dans l'URL).
"""

import requests
from flask import Blueprint, render_template, jsonify, request, g

from src.WebUI.auth import login_required, API_BASE
from src.variables import (
    MODULES_REGISTERY, WORKFLOWS_REGISTERY,
    WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION,
    APP_AUTHOR, APP_LICENSE, APP_REPOSITORY,
)

account_bp = Blueprint("account", __name__, url_prefix="/account")


def _variables():
    return {
        "WEB_SERVER_HOST": WEB_SERVER_HOST,
        "WEB_SERVER_PORT": WEB_SERVER_PORT,
        "APP_NAME":        APP_NAME,
        "APP_VERSION":     APP_VERSION,
        "APP_DESCRIPTION": APP_DESCRIPTION,
        "APP_AUTHOR":      APP_AUTHOR,
        "APP_LICENSE":     APP_LICENSE,
        "APP_REPOSITORY":  APP_REPOSITORY,
        "MODULES":         MODULES_REGISTERY,
        "WORKFLOWS":       WORKFLOWS_REGISTERY,
    }


def _api(method: str, path: str, **kwargs):
    try:
        resp = getattr(requests, method)(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {g.token}"},
            timeout=5,
            **kwargs,
        )
        return resp.json(), resp.status_code
    except requests.exceptions.ConnectionError:
        return {"error": "API inaccessible"}, 503
    except Exception as e:
        return {"error": str(e)}, 500


@account_bp.route("")
@login_required
def account_page():
    profile, status = _api("get", "/auth/me")
    if status != 200:
        profile = {}
    return render_template("account.html", profile=profile, **_variables())


@account_bp.route("/profile", methods=["POST"])
@login_required
def update_profile():
    """Relais vers PATCH /auth/me — display_name/email du user courant."""
    body = request.get_json(silent=True) or {}
    try:
        resp = requests.patch(
            f"{API_BASE}/auth/me",
            headers={"Authorization": f"Bearer {g.token}"},
            json=body,
            timeout=5,
        )
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "API inaccessible"}), 503


@account_bp.route("/password", methods=["POST"])
@login_required
def update_password():
    """Relais vers POST /auth/me/password — changement de mot de passe."""
    body = request.get_json(silent=True) or {}
    data, status = _api("post", "/auth/me/password", json=body)
    return jsonify(data), status