"""
src/WebUI/admin.py
──────────────────
Blueprint /admin — gestion des utilisateurs et permissions.
Accessible uniquement aux users ayant users_perm.
"""

import requests
from flask import Blueprint, render_template, jsonify, request, g, redirect, url_for, abort
from functools import wraps

from src.WebUI.auth import login_required, API_BASE
from src.variables import (
    MODULES_REGISTERY, WORKFLOWS_REGISTERY,
    WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION,
    APP_AUTHOR, APP_LICENSE, APP_REPOSITORY,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ALL_PERMS = {
    "modules":    ["*"],
    "rapports":   ["*", "read", "write"],
    "missions":   ["*", "read", "write"],
    "workflows":  ["*", "read", "write"],
    "ressources": ["*", "read", "write"],
    "users":      ["*", "read", "write"],
}

PERM_FIELDS = {
    "modules":    "modules",
    "rapports":   "rapports_perm",
    "missions":   "missions_perm",
    "workflows":  "worklows_perm",
    "ressources": "ressources_perm",
    "users":      "users_perm",
}


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


def admin_required(f):
    """Vérifie que le user a la permission users:read via l'API."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        try:
            resp = requests.get(
                f"{API_BASE}/users",
                headers={"Authorization": f"Bearer {g.token}"},
                timeout=5,
            )
        except requests.exceptions.ConnectionError:
            abort(503)
        if resp.status_code == 401:
            return redirect(url_for("login_page"))
        if resp.status_code == 403:
            abort(403)
        return f(*args, **kwargs)
    return decorated


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


# ── Gestionnaire d'erreurs propres ────────────────────────────────────────────

# Les erreurs 403/503 de ce blueprint sont désormais gérées par les
# error handlers globaux de server.py (template error.html unique).


# ── Routes ────────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
@admin_required
def users_page():
    users, status = _api("get", "/users")
    if status != 200:
        users = []
    return render_template(
        "admin_users.html",
        users=users,
        all_perms=ALL_PERMS,
        perm_fields=PERM_FIELDS,
        **_variables(),
    )


@admin_bp.route("/users/<int:user_id>/perms", methods=["POST"])
@login_required
def update_perms(user_id: int):
    body = request.get_json(silent=True) or {}
    data, status = _api("post", f"/admin/users/{user_id}/perms", json=body)
    return jsonify(data), status


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@login_required
def delete_user(user_id: int):
    data, status = _api("delete", f"/admin/users/{user_id}")
    return jsonify(data), status