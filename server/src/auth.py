"""
auth.py — mis à jour avec support des clés de chiffrement par utilisateur.
"""

import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from src.db import load_users, save_users
from src.crypto_utils import generate_user_key          # ← nouveau


DATA_PATH         = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')
SECRET_KEY        = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
TOKEN_EXPIRY_HOURS = float(os.environ.get('TOKEN_EXPIRY_HOURS', 24))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _find_user(users: list, username: str) -> dict | None:
    return next((u for u in users if u['username'] == username), None)

def _next_id(users: list) -> int:
    return max((u['id'] for u in users), default=0) + 1


# ─── Routes ───────────────────────────────────────────────────────────────────

def register():
    """POST /auth/register  { username, password }"""
    body     = request.get_json(silent=True) or {}
    username = body.get('username', '').strip()
    password = body.get('password', '')
    users    = load_users()

    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400
    if len(password) < 8:
        return jsonify({'error': 'password must be at least 8 characters'}), 400
    if _find_user(users, username):
        return jsonify({'error': 'username already taken'}), 409

    new_user = {
        'id':              _next_id(users),
        'username':        username,
        'password':        generate_password_hash(password),
        'encryption_key':  generate_user_key(),          # ← clé AES-256 unique
        'display_name':    username,
        'email':           '',
        'disabled':        False,
        # Permissions minimales par défaut
        'modules':         [],
        'rapports_perm':   ['read'],
        'missions_perm':   ['read'],
        'worklows_perm':   ['read'],
        'ressources_perm': ['read'],
        'users_perm':      [],
    }
    users.append(new_user)
    save_users(users)

    return jsonify({
        'message':  'user created',
        'username': username,
        'id':       new_user['id'],
    }), 201


def login():
    """POST /auth/login  { username, password }"""
    body     = request.get_json(silent=True) or {}
    username = body.get('username', '').strip()
    password = body.get('password', '')

    if not username or not password:
        return jsonify({'error': 'username and password required'}), 400

    users = load_users()
    user  = _find_user(users, username)

    if not user or not check_password_hash(user['password'], password):
        return jsonify({'error': 'invalid credentials'}), 401

    if user.get('disabled'):
        return jsonify({'error': 'account disabled'}), 403

    # Génère la clé si absente (migration users existants)
    if not user.get('encryption_key'):
        user['encryption_key'] = generate_user_key()
        save_users(users)

    token = jwt.encode(
        {
            'sub':      str(user['id']),
            'username': user['username'],
            'permissions': {
                'modules':    user.get('modules', []),
                'rapports':   user.get('rapports_perm', []),
                'missions':   user.get('missions_perm', []),
                'workflows':  user.get('worklows_perm', []),
                'ressources': user.get('ressources_perm', []),
                'users':      user.get('users_perm', []),
            },
            'exp': datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRY_HOURS),
        },
        SECRET_KEY,
        algorithm='HS256',
    )

    return jsonify({
        'token':   token,
        'enc_key': user['encryption_key'],   # ← clé AES transmise au client (HTTPS only !)
    }), 200


# ─── Décorateurs ──────────────────────────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'missing or malformed token'}), 401
        token = auth_header.split(' ', 1)[1]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'token expired'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': 'invalid token'}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated


def require_permission(resource: str, action: str):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            perms   = request.current_user.get('permissions', {})
            allowed = perms.get(resource, [])
            if '*' not in allowed and action not in allowed:
                return jsonify({'error': f'permission denied: {resource}:{action}'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ─── Gestion de profil personnel (tout user connecté, sur SON propre compte) ──

def _safe_profile(u: dict) -> dict:
    """Profil sans password ni encryption_key — pour affichage uniquement."""
    return {
        'id':           u['id'],
        'username':     u['username'],
        'display_name': u.get('display_name', u['username']),
        'email':        u.get('email', ''),
        'disabled':     u.get('disabled', False),
    }


@token_required
def get_my_profile():
    """GET /auth/me — profil du user connecté."""
    users = load_users()
    user  = next((u for u in users if str(u['id']) == str(request.current_user.get('sub'))), None)
    if not user:
        return jsonify({'error': 'user not found'}), 404
    return jsonify(_safe_profile(user)), 200


@token_required
def update_my_profile():
    """
    PATCH /auth/me   Body JSON : { "display_name": "...", "email": "..." }
    Un user ne peut modifier que son propre profil — aucune route ne permet
    de cibler un autre id ici (la gestion des autres comptes passe par
    /admin/users, réservée à users:write).
    """
    body  = request.get_json(silent=True) or {}
    users = load_users()
    user  = next((u for u in users if str(u['id']) == str(request.current_user.get('sub'))), None)
    if not user:
        return jsonify({'error': 'user not found'}), 404

    if 'display_name' in body:
        display_name = str(body['display_name']).strip()
        if not display_name:
            return jsonify({'error': 'display_name cannot be empty'}), 400
        user['display_name'] = display_name

    if 'email' in body:
        user['email'] = str(body['email']).strip()

    save_users(users)
    return jsonify(_safe_profile(user)), 200


@token_required
def update_my_password():
    """
    POST /auth/me/password
    Body JSON : { "current_password": "...", "new_password": "..." }
    Vérifie le mot de passe actuel avant tout changement — un user ne
    peut jamais changer son mot de passe sans le connaître (contrairement
    à la réinitialisation admin, qui contourne volontairement cette
    vérification puisque l'admin agit pour un compte qui n'est pas le sien).
    """
    body             = request.get_json(silent=True) or {}
    current_password = body.get('current_password', '')
    new_password     = body.get('new_password', '')

    if not current_password or not new_password:
        return jsonify({'error': 'current_password and new_password required'}), 400
    if len(new_password) < 8:
        return jsonify({'error': 'new_password must be at least 8 characters'}), 400

    users = load_users()
    user  = next((u for u in users if str(u['id']) == str(request.current_user.get('sub'))), None)
    if not user:
        return jsonify({'error': 'user not found'}), 404

    if not check_password_hash(user['password'], current_password):
        return jsonify({'error': 'current password is incorrect'}), 401

    user['password'] = generate_password_hash(new_password)
    save_users(users)
    return jsonify({'ok': True}), 200