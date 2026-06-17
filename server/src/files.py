"""
files.py
────────
Endpoints Flask pour accéder aux fichiers chiffrés, avec notion d'OWNER.

Chaque fichier .enc stocké sur disque a la forme :
  {
    "owner_id":      "<id du créateur>",
    "nonce":         "<base64url>",
    "ciphertext":    "<base64url>",
    "original_name": "<nom de fichier>"
  }

owner_id est en clair (métadonnée), jamais le contenu.

Règle d'accès en lecture :
  - owner_id == current_user.id        → on déchiffre avec la clé du current_user
  - sinon, permission '*' sur la ressource → on emprunte la clé de l'owner
  - sinon                               → 403

Règle d'accès en écriture (PUT) :
  - Un nouveau fichier est toujours créé avec owner_id = current_user.id
  - Un fichier existant ne peut être modifié que par son owner, OU par un
    user disposant de la permission '*' (write) sur la ressource — dans ce
    cas il est re-chiffré avec la clé de l'OWNER ORIGINAL (le fichier ne
    change pas de propriétaire silencieusement).

Structure sur disque :
  /app/data/
    missions/<mission_name>/<mission_id>.json.enc
    reports/<filename>.{pdf,html,json}.enc
    workflows/<filename>.{pdf,html,json}.enc
"""

import json
import os
from pathlib import Path

from flask import Blueprint, jsonify, request, abort
from src.auth import token_required
from src.db import load_users
from src.crypto_utils import resolve_decryption_key, resolve_encryption_key

# ─── Config ───────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get('DATA_DIR', '/app/data'))

files_bp = Blueprint('files', __name__, url_prefix='/files')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_user_key(user_id: str, users: list[dict]) -> str | None:
    user = next((u for u in users if str(u['id']) == str(user_id)), None)
    return user.get('encryption_key') if user else None

def _has_perm(perm_key: str, action: str) -> bool:
    perms   = request.current_user.get('permissions', {})
    allowed = perms.get(perm_key, [])
    return '*' in allowed or action in allowed

def _has_wildcard(perm_key: str) -> bool:
    perms   = request.current_user.get('permissions', {})
    allowed = perms.get(perm_key, [])
    return '*' in allowed

def _check_perm(perm_key: str, action: str):
    if not _has_perm(perm_key, action):
        abort(403, description=f"Permission refusée : {perm_key}:{action}")

def _safe_name(name: str) -> str:
    return Path(name).name

def _ensure_enc(name: str) -> str:
    return name if name.endswith('.enc') else name + '.enc'

def _current_user_id() -> str:
    return request.current_user.get('sub')

def _current_user_key(users: list[dict]) -> str | None:
    return _get_user_key(_current_user_id(), users)


def _read_envelope(file_path: Path) -> dict:
    with open(file_path, 'r') as f:
        return json.load(f)


def _build_payload(file_path: Path, perm_key: str) -> dict:
    """
    Lit l'enveloppe d'un fichier, résout la clé de déchiffrement selon
    owner_id + permissions du current_user, et retourne le payload
    { nonce, ciphertext, original_name, enc_key } prêt pour le client.
    Lève 403 si ni owner ni permission '*'.
    """
    envelope = _read_envelope(file_path)
    owner_id = envelope.get('owner_id')

    users          = load_users()
    current_id     = _current_user_id()
    current_key    = _current_user_key(users)
    has_wildcard   = _has_wildcard(perm_key)

    if not current_key:
        abort(500, description="Clé de chiffrement manquante pour cet utilisateur")

    resolved_key = resolve_decryption_key(
        current_user_id=current_id,
        current_user_key=current_key,
        owner_id=owner_id,
        has_wildcard_perm=has_wildcard,
        users=users,
    )

    if resolved_key is None:
        abort(403, description="Vous n'êtes pas le propriétaire de ce fichier "
                                "et ne disposez pas de la permission '*' requise")

    return {
        'nonce':         envelope['nonce'],
        'ciphertext':    envelope['ciphertext'],
        'original_name': envelope.get('original_name'),
        'enc_key':       resolved_key,
        'owner_id':      owner_id,   # informatif, non sensible
    }


def _save_enc(file_path: Path, body: dict, perm_key: str):
    """
    Persiste un payload chiffré sur disque, avec gestion de l'owner :
      - fichier inexistant     → owner = current_user (nouveau fichier)
      - fichier existant,
          owner == current     → ré-écriture normale, owner conservé
          owner != current,
          permission '*'       → ré-écriture autorisée, owner ORIGINAL conservé
          owner != current,
          pas de '*'            → 403
    Le body reçu ({nonce, ciphertext, original_name}) est déjà chiffré
    côté client AVEC LA CLÉ DU CURRENT_USER (jamais avec la clé emprunté
    d'un autre owner — emprunter une clé en écriture re-chiffrerait avec
    la mauvaise identité ; ce cas n'est donc permis qu'en lecture).
    """
    users       = load_users()
    current_id  = _current_user_id()

    if file_path.exists():
        envelope = _read_envelope(file_path)
        owner_id = envelope.get('owner_id')

        if str(owner_id) != str(current_id) and not _has_wildcard(perm_key):
            abort(403, description="Seul le propriétaire (ou un accès '*') "
                                    "peut modifier ce fichier")
        # Le owner_id ne change jamais lors d'une mise à jour, même si un
        # admin '*' a effectué la modification — l'attribution reste stable.
        final_owner = owner_id
    else:
        final_owner = current_id

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump({
            'owner_id':      final_owner,
            'nonce':         body['nonce'],
            'ciphertext':    body['ciphertext'],
            'original_name': body['original_name'],
        }, f)


def _can_list(envelope_owner: str, perm_key: str) -> bool:
    """Un fichier apparaît dans un listing si on en est owner OU si on a '*'."""
    return str(envelope_owner) == str(_current_user_id()) or _has_wildcard(perm_key)


# ══════════════════════════════════════════════════════════════════════════════
#  MISSIONS  (2 niveaux : missions/<name>/<id>.json)
# ══════════════════════════════════════════════════════════════════════════════

@files_bp.route('/missions', methods=['GET'])
@token_required
def list_missions():
    """
    Liste toutes les missions visibles par le current_user
    (dont il est owner, ou pour lesquelles il a missions:* ).
    Retourne : { "mission_name": [{name, original_name, size}, ...], ... }
    """
    _check_perm('missions', 'read')

    missions_dir = DATA_DIR / 'missions'
    if not missions_dir.exists():
        return jsonify({})

    result = {}
    for mission_dir in sorted(missions_dir.iterdir()):
        if not mission_dir.is_dir():
            continue
        files = []
        for p in sorted(mission_dir.glob('*.enc')):
            try:
                envelope = _read_envelope(p)
            except Exception:
                continue
            if not _can_list(envelope.get('owner_id'), 'missions'):
                continue
            files.append({
                "name":          p.name,
                "original_name": p.stem,
                "size":          p.stat().st_size,
            })
        if files:
            result[mission_dir.name] = files

    return jsonify(result)


@files_bp.route('/missions/<mission_name>', methods=['GET'])
@token_required
def list_mission_files(mission_name: str):
    _check_perm('missions', 'read')

    mission_dir = DATA_DIR / 'missions' / _safe_name(mission_name)
    if not mission_dir.exists() or not mission_dir.is_dir():
        abort(404, description=f"Mission introuvable : {mission_name}")

    files = []
    for p in sorted(mission_dir.glob('*.enc')):
        try:
            envelope = _read_envelope(p)
        except Exception:
            continue
        if not _can_list(envelope.get('owner_id'), 'missions'):
            continue
        files.append({
            "name":          p.name,
            "original_name": p.stem,
            "size":          p.stat().st_size,
        })
    return jsonify(files)


@files_bp.route('/missions/<mission_name>/<filename>', methods=['GET'])
@token_required
def get_mission_file(mission_name: str, filename: str):
    _check_perm('missions', 'read')

    file_path = DATA_DIR / 'missions' / _safe_name(mission_name) / _ensure_enc(_safe_name(filename))
    if not file_path.exists():
        abort(404, description=f"Fichier introuvable : {mission_name}/{filename}")

    return jsonify(_build_payload(file_path, 'missions'))


@files_bp.route('/missions/<mission_name>/<filename>', methods=['PUT'])
@token_required
def upload_mission_file(mission_name: str, filename: str):
    _check_perm('missions', 'write')

    body = request.get_json(silent=True) or {}
    if not all(k in body for k in ('nonce', 'ciphertext', 'original_name')):
        abort(400, description="Body requis : { nonce, ciphertext, original_name }")

    file_path = DATA_DIR / 'missions' / _safe_name(mission_name) / _ensure_enc(_safe_name(filename))
    _save_enc(file_path, body, 'missions')
    return jsonify({'message': 'Fichier enregistré', 'path': str(file_path)}), 201


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTS & WORKFLOWS  (1 niveau : <category>/<file>)
# ══════════════════════════════════════════════════════════════════════════════

FLAT_CATEGORIES = {
    'reports':   ('reports',   'rapports'),
    'workflows': ('workflows', 'workflows'),
}

@files_bp.route('/<category>', methods=['GET'])
@token_required
def list_flat_files(category: str):
    if category not in FLAT_CATEGORIES:
        abort(404, description=f"Catégorie inconnue : {category}")

    folder, perm_key = FLAT_CATEGORIES[category]
    _check_perm(perm_key, 'read')

    cat_dir = DATA_DIR / folder
    if not cat_dir.exists():
        return jsonify([])

    files = []
    for p in sorted(cat_dir.glob('*.enc')):
        try:
            envelope = _read_envelope(p)
        except Exception:
            continue
        if not _can_list(envelope.get('owner_id'), perm_key):
            continue
        files.append({
            "name":          p.name,
            "original_name": p.stem,
            "size":          p.stat().st_size,
        })
    return jsonify(files)


@files_bp.route('/<category>/<filename>', methods=['GET'])
@token_required
def get_flat_file(category: str, filename: str):
    if category not in FLAT_CATEGORIES:
        abort(404, description=f"Catégorie inconnue : {category}")

    folder, perm_key = FLAT_CATEGORIES[category]
    _check_perm(perm_key, 'read')

    file_path = DATA_DIR / folder / _ensure_enc(_safe_name(filename))
    if not file_path.exists():
        abort(404, description=f"Fichier introuvable : {filename}")

    return jsonify(_build_payload(file_path, perm_key))


@files_bp.route('/<category>/<filename>', methods=['PUT'])
@token_required
def upload_flat_file(category: str, filename: str):
    if category not in FLAT_CATEGORIES:
        abort(404, description=f"Catégorie inconnue : {category}")

    folder, perm_key = FLAT_CATEGORIES[category]
    _check_perm(perm_key, 'write')

    body = request.get_json(silent=True) or {}
    if not all(k in body for k in ('nonce', 'ciphertext', 'original_name')):
        abort(400, description="Body requis : { nonce, ciphertext, original_name }")

    file_path = DATA_DIR / folder / _ensure_enc(_safe_name(filename))
    _save_enc(file_path, body, perm_key)
    return jsonify({'message': 'Fichier enregistré', 'path': str(file_path)}), 201


@files_bp.route('/<category>/<filename>', methods=['DELETE'])
@token_required
def delete_flat_file(category: str, filename: str):
    if category not in FLAT_CATEGORIES:
        abort(404, description=f"Catégorie inconnue : {category}")

    folder, perm_key = FLAT_CATEGORIES[category]
    _check_perm(perm_key, 'write')

    file_path = DATA_DIR / folder / _ensure_enc(_safe_name(filename))
    if not file_path.exists():
        abort(404, description=f"Fichier introuvable : {filename}")

    envelope = _read_envelope(file_path)
    owner_id = envelope.get('owner_id')
    if str(owner_id) != str(_current_user_id()) and not _has_wildcard(perm_key):
        abort(403, description="Seul le propriétaire (ou un accès '*') peut supprimer ce fichier")

    file_path.unlink()
    return jsonify({'message': 'Fichier supprimé'}), 200


# ─── Erreurs ──────────────────────────────────────────────────────────────────

@files_bp.errorhandler(400)
@files_bp.errorhandler(403)
@files_bp.errorhandler(404)
@files_bp.errorhandler(500)
def handle_error(e):
    return jsonify({'error': e.description}), e.code