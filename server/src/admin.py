"""
src/admin.py  (côté API Flask :5001)
──────────────────────────────────────
Routes admin pour la gestion des utilisateurs.

  GET    /users                          → liste (sans password ni enc_key)
  POST   /admin/users/<id>/perms         → mise à jour des permissions
  DELETE /admin/users/<id>               → suppression d'un user

Toutes ces routes nécessitent @token_required.
/admin/* nécessitent users:write ou users:*.
"""

from flask import Blueprint, jsonify, request
from src.auth import token_required, require_permission
from src.db import load_users, save_users

admin_bp = Blueprint("admin", __name__)

# Mapping clé JSON → champ dans users.json
PERM_TO_FIELD = {
    "modules":    "modules",
    "rapports":   "rapports_perm",
    "missions":   "missions_perm",
    "workflows":  "worklows_perm",   # typo conservée pour compat
    "ressources": "ressources_perm",
    "users":      "users_perm",
}

VALID_PERMS = {"*", "read", "write"}


def _safe_user(u: dict) -> dict:
    """Retourne un user sans password ni encryption_key."""
    return {
        "id":              u["id"],
        "username":        u["username"],
        "modules":         u.get("modules", []),
        "rapports_perm":   u.get("rapports_perm", []),
        "missions_perm":   u.get("missions_perm", []),
        "worklows_perm":   u.get("worklows_perm", []),
        "ressources_perm": u.get("ressources_perm", []),
        "users_perm":      u.get("users_perm", []),
    }


# ── GET /users ────────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@token_required
@require_permission("users", "read")
def list_users():
    users = load_users()
    return jsonify([_safe_user(u) for u in users])


# ── POST /admin/users/<id>/perms ──────────────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>/perms", methods=["POST"])
@token_required
@require_permission("users", "write")
def update_perms(user_id: int):
    """
    Body JSON :
    {
      "rapports":   ["read"],
      "missions":   ["*"],
      "workflows":  [],
      "ressources": ["read", "write"],
      "users":      [],
      "modules":    []
    }
    Seules les clés présentes dans PERM_TO_FIELD sont acceptées.
    Les valeurs invalides sont ignorées.
    """
    body  = request.get_json(silent=True) or {}
    users = load_users()
    user  = next((u for u in users if u["id"] == user_id), None)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    # Applique les nouvelles permissions
    for res_key, field in PERM_TO_FIELD.items():
        if res_key not in body:
            continue
        raw  = body[res_key]
        # Filtre les valeurs invalides
        vals = [v for v in raw if v in VALID_PERMS]
        # Cohérence : si "*" présent, on vide le reste
        if "*" in vals:
            vals = ["*"]
        user[field] = vals

    save_users(users)
    return jsonify({"ok": True, "username": user["username"], **_safe_user(user)})


# ── DELETE /admin/users/<id> ──────────────────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@token_required
@require_permission("users", "write")
def delete_user(user_id: int):
    users    = load_users()
    filtered = [u for u in users if u["id"] != user_id]

    if len(filtered) == len(users):
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    # Interdit de se supprimer soi-même
    current_id = request.current_user.get("sub")
    if str(user_id) == str(current_id):
        return jsonify({"error": "Vous ne pouvez pas supprimer votre propre compte"}), 403

    save_users(filtered)
    return jsonify({"ok": True, "deleted_id": user_id})