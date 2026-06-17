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