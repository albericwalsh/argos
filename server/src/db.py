import json
import os

from werkzeug.security import generate_password_hash

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'users.json')

DEFAULT_ADMIN = {
    'id': 1,
    'username': 'admin',
    'password': generate_password_hash('admin123'),
    'display_name': 'Administrateur',
    'email': '',
    'disabled': False,
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


# ─── Migration de schéma ──────────────────────────────────────────────────────

USER_FIELD_DEFAULTS = {
    'display_name':    '',
    'email':            '',
    'disabled':         False,
    'modules':          [],
    'rapports_perm':    [],
    'missions_perm':    [],
    'worklows_perm':    [],
    'ressources_perm':  [],
    'users_perm':       [],
}

def _migrate_user(user: dict) -> dict:
    """
    Complète un user existant avec les nouveaux champs (display_name,
    email, disabled) sans rien écraser, pour rester compatible avec les
    comptes créés avant l'ajout de la gestion de profil/blocage.
    """
    changed = False
    for field, default in USER_FIELD_DEFAULTS.items():
        if field not in user:
            user[field] = default
            changed = True
    return user, changed


def _migrate_all(users: list) -> tuple[list, bool]:
    any_changed = False
    for u in users:
        _, changed = _migrate_user(u)
        any_changed = any_changed or changed
    return users, any_changed


# ─── Initialisation ───────────────────────────────────────────────────────────

def init_users(reset: bool = False) -> None:
    """
    Initialise users.json si nécessaire.

    Cas traités :
      - fichier absent
      - fichier corrompu / format invalide
      - liste vide
      - admin manquant
      - schéma obsolète (migration des champs manquants : display_name,
        email, disabled)
      - reset forcé (repart de DEFAULT_USERS)
    """
    if reset:
        print('[db] reset forcé → restauration des utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    if not os.path.exists(DATA_PATH):
        print('[db] users.json absent → création avec utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    try:
        users = _load_raw()
    except (json.JSONDecodeError, ValueError) as e:
        print(f'[db] users.json invalide ({e}) → réinitialisation')
        _save_raw(DEFAULT_USERS)
        return

    if not users:
        print('[db] users.json vide → injection des utilisateurs par défaut')
        _save_raw(DEFAULT_USERS)
        return

    has_admin = any(u.get('username') == 'admin' for u in users)
    if not has_admin:
        print('[db] admin absent → injection du compte admin')
        users.insert(0, DEFAULT_ADMIN)
        _save_raw(users)
        return

    users, migrated = _migrate_all(users)
    if migrated:
        print('[db] schéma utilisateur obsolète → migration des champs manquants')
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


def next_user_id(users: list) -> int:
    """Calcule le prochain id disponible pour un nouveau compte."""
    return max((u['id'] for u in users), default=0) + 1