"""
src/admin.py  (côté API Flask :5001)
──────────────────────────────────────
Routes admin pour la gestion des utilisateurs.

  GET    /users                              → liste (sans password ni enc_key)
  POST   /admin/users                        → création d'un nouveau compte
  POST   /admin/users/<id>/perms             → mise à jour des permissions
  POST   /admin/users/<id>/profile           → display_name/email (admin → autre user)
  POST   /admin/users/<id>/disable           → bloque un compte
  POST   /admin/users/<id>/enable            → débloque un compte
  POST   /admin/users/<id>/reset-password    → réinitialise le mot de passe (admin)
  DELETE /admin/users/<id>                   → suppression d'un user

Toutes nécessitent users:write, sauf le listing (users:read).
"""

from flask import Blueprint, jsonify, request
from werkzeug.security import generate_password_hash

from src.auth import token_required, require_permission
from src.db import load_users, save_users, next_user_id
from src.crypto_utils import generate_user_key

admin_bp = Blueprint("admin", __name__)

PERM_TO_FIELD = {
    "modules":    "modules",
    "rapports":   "rapports_perm",
    "missions":   "missions_perm",
    "workflows":  "worklows_perm",
    "ressources": "ressources_perm",
    "users":      "users_perm",
}

VALID_PERMS = {"*", "read", "write"}


def _safe_user(u: dict) -> dict:
    return {
        "id":              u["id"],
        "username":        u["username"],
        "display_name":    u.get("display_name", u["username"]),
        "email":           u.get("email", ""),
        "disabled":        u.get("disabled", False),
        "modules":         u.get("modules", []),
        "rapports_perm":   u.get("rapports_perm", []),
        "missions_perm":   u.get("missions_perm", []),
        "worklows_perm":   u.get("worklows_perm", []),
        "ressources_perm": u.get("ressources_perm", []),
        "users_perm":      u.get("users_perm", []),
    }


def _find_or_404(users: list, user_id: int):
    return next((u for u in users if u["id"] == user_id), None)


# ── Listing ────────────────────────────────────────────────────────────────────

@admin_bp.route("/users", methods=["GET"])
@token_required
@require_permission("users", "read")
def list_users():
    users = load_users()
    return jsonify([_safe_user(u) for u in users])


# ── Création ───────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/users", methods=["POST"])
@token_required
@require_permission("users", "write")
def create_user():
    """
    POST /admin/users
    Body JSON : { "username": "...", "password": "...", "display_name": "..." (optionnel) }
    Crée un compte avec des permissions vides par défaut — l'admin les
    ajuste ensuite via /admin/users/<id>/perms, comme pour tout autre user.
    """
    body         = request.get_json(silent=True) or {}
    username     = body.get("username", "").strip()
    password     = body.get("password", "")
    display_name = body.get("display_name", "").strip() or username

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    users = load_users()
    if any(u["username"] == username for u in users):
        return jsonify({"error": "username already taken"}), 409

    new_user = {
        "id":              next_user_id(users),
        "username":        username,
        "password":        generate_password_hash(password),
        "encryption_key":  generate_user_key(),
        "display_name":    display_name,
        "email":           "",
        "disabled":        False,
        "modules":         [],
        "rapports_perm":   [],
        "missions_perm":   [],
        "worklows_perm":   [],
        "ressources_perm": [],
        "users_perm":      [],
    }
    users.append(new_user)
    save_users(users)

    return jsonify({"ok": True, **_safe_user(new_user)}), 201


# ── Permissions ────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>/perms", methods=["POST"])
@token_required
@require_permission("users", "write")
def update_perms(user_id: int):
    body  = request.get_json(silent=True) or {}
    users = load_users()
    user  = _find_or_404(users, user_id)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    for res_key, field in PERM_TO_FIELD.items():
        if res_key not in body:
            continue
        raw  = body[res_key]
        vals = [v for v in raw if v in VALID_PERMS]
        if "*" in vals:
            vals = ["*"]
        user[field] = vals

    save_users(users)
    return jsonify({"ok": True, **_safe_user(user)})


# ── Profil (admin modifie un AUTRE user) ───────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>/profile", methods=["POST"])
@token_required
@require_permission("users", "write")
def update_user_profile(user_id: int):
    """
    POST /admin/users/<id>/profile
    Body JSON : { "display_name": "...", "email": "..." }
    Distinct de PATCH /auth/me : ici l'admin agit sur un compte qui n'est
    pas le sien, d'où la permission users:write requise.
    """
    body  = request.get_json(silent=True) or {}
    users = load_users()
    user  = _find_or_404(users, user_id)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    if "display_name" in body:
        display_name = str(body["display_name"]).strip()
        if not display_name:
            return jsonify({"error": "display_name cannot be empty"}), 400
        user["display_name"] = display_name

    if "email" in body:
        user["email"] = str(body["email"]).strip()

    save_users(users)
    return jsonify({"ok": True, **_safe_user(user)})


# ── Blocage / déblocage ─────────────────────────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>/disable", methods=["POST"])
@token_required
@require_permission("users", "write")
def disable_user(user_id: int):
    """
    Bloque un compte : login() refuse désormais toute connexion pour ce
    user (vérifié côté auth.py). Les sessions déjà ouvertes (JWT existants,
    non révocables sans store de sessions) restent valides jusqu'à
    expiration — limite connue, acceptable pour ce projet.
    """
    users = load_users()
    user  = _find_or_404(users, user_id)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    current_id = request.current_user.get("sub")
    if str(user_id) == str(current_id):
        return jsonify({"error": "Vous ne pouvez pas bloquer votre propre compte"}), 403

    user["disabled"] = True
    save_users(users)
    return jsonify({"ok": True, **_safe_user(user)})


@admin_bp.route("/admin/users/<int:user_id>/enable", methods=["POST"])
@token_required
@require_permission("users", "write")
def enable_user(user_id: int):
    users = load_users()
    user  = _find_or_404(users, user_id)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    user["disabled"] = False
    save_users(users)
    return jsonify({"ok": True, **_safe_user(user)})


# ── Réinitialisation de mot de passe (admin → autre user) ─────────────────────

@admin_bp.route("/admin/users/<int:user_id>/reset-password", methods=["POST"])
@token_required
@require_permission("users", "write")
def reset_password(user_id: int):
    """
    POST /admin/users/<id>/reset-password
    Body JSON : { "new_password": "..." } (optionnel — si absent, un mot
    de passe temporaire est généré aléatoirement et renvoyé une seule fois
    dans la réponse, pour être communiqué au user par l'admin).

    Contrairement à update_my_password() (auth.py), aucune vérification
    de l'ancien mot de passe : l'admin agit délibérément sans le connaître.
    """
    import secrets

    body         = request.get_json(silent=True) or {}
    new_password = body.get("new_password", "").strip()

    generated = False
    if not new_password:
        new_password = secrets.token_urlsafe(9)  # ~12 caractères lisibles
        generated = True
    elif len(new_password) < 8:
        return jsonify({"error": "new_password must be at least 8 characters"}), 400

    users = load_users()
    user  = _find_or_404(users, user_id)

    if not user:
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    user["password"] = generate_password_hash(new_password)
    save_users(users)

    response = {"ok": True, "username": user["username"]}
    if generated:
        # Le mot de passe en clair n'est renvoyé qu'ici, qu'une seule fois,
        # jamais journalisé ni stocké — à communiquer immédiatement à l'user.
        response["generated_password"] = new_password
    return jsonify(response)


# ── Suppression ────────────────────────────────────────────────────────────────

@admin_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@token_required
@require_permission("users", "write")
def delete_user(user_id: int):
    users    = load_users()
    filtered = [u for u in users if u["id"] != user_id]

    if len(filtered) == len(users):
        return jsonify({"error": f"Utilisateur {user_id} introuvable"}), 404

    current_id = request.current_user.get("sub")
    if str(user_id) == str(current_id):
        return jsonify({"error": "Vous ne pouvez pas supprimer votre propre compte"}), 403

    save_users(filtered)
    return jsonify({"ok": True, "deleted_id": user_id})