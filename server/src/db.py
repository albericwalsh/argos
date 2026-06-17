import json
import os

from werkzeug.security import generate_password_hash

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')

DEFAULT_ADMIN = {
    'id': 1,
    'username': 'admin',
    'password': generate_password_hash('admin123'),
    'modules': ['*'],
    'rapports_perm': ['*'],
    'missions_perm': ['*'],
    'worklows_perm': ['*'],
    'ressources_perm': ['*'],
    'users_perm': ['*'],
}

DEFAULT_USERS = [DEFAULT_ADMIN]


# ─── Helpers bas niveau ───────────────────────────────────────────────────────

def _load_raw() -> list:
    with open(DATA_PATH, 'r') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError('users.json doit être une liste JSON')
    return data

def _save_raw(users: list) -> None:
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, 'w') as f:
        json.dump(users, f, indent=2)


# ─── Initialisation ───────────────────────────────────────────────────────────

def init_users(reset: bool = False) -> None:
    """
    Initialise users.json si nécessaire.

    Cas traités :
      - fichier absent
      - fichier corrompu / format invalide
      - liste vide
      - admin manquant
      - reset forcé (repart de DEFAULT_USERS)

    Args:
        reset: Si True, écrase complètement users.json avec DEFAULT_USERS.
    """
    if reset:
        print('[db] reset forcé → restauration des utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    # Fichier absent
    if not os.path.exists(DATA_PATH):
        print('[db] users.json absent → création avec utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    # Fichier présent mais potentiellement corrompu
    try:
        users = _load_raw()
    except (json.JSONDecodeError, ValueError) as e:
        print(f'[db] users.json invalide ({e}) → réinitialisation')
        _save_raw(DEFAULT_USERS)
        return

    # Liste vide
    if not users:
        print('[db] users.json vide → injection des utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    # Admin manquant
    has_admin = any(u.get('username') == 'admin' for u in users)
    if not has_admin:
        print('[db] admin absent → injection du compte admin')
        # Préserve les autres users, insère admin en tête
        users.insert(0, DEFAULT_ADMIN)
        _save_raw(users)
        return

    print('[db] users.json OK — aucune action requise')


def load_users() -> list:
    """Charge et retourne la liste des users (après init garantie)."""
    init_users()
    return _load_raw()

def save_users(users: list) -> None:
    """Sauvegarde la liste des users."""
    _save_raw(users)