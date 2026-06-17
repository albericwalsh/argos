#!/usr/bin/env python3
"""
scripts/encrypt_files.py
─────────────────────────
Chiffre tous les fichiers JSON/PDF/HTML existants.

Structure attendue :
  data/
    missions/<mission_name>/<mission_id>.json   ← sous-dossiers
    reports/<filename>.pdf
    workflows/<filename>.html

Usage :
    python scripts/encrypt_files.py
    python scripts/encrypt_files.py --user alice
    python scripts/encrypt_files.py --dry-run
    python scripts/encrypt_files.py --delete
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.crypto_utils import encrypt_file
from src.db import load_users

DATA_DIR   = ROOT / 'data'
EXTENSIONS = ['.json', '.pdf', '.html']


def get_user_key(username: str) -> str:
    users = load_users()
    user  = next((u for u in users if u['username'] == username), None)
    if not user:
        print(f"[ERREUR] Utilisateur '{username}' introuvable")
        sys.exit(1)
    key = user.get('encryption_key')
    if not key:
        print(f"[ERREUR] '{username}' n'a pas de clé. Exécutez d'abord generate_keys.py")
        sys.exit(1)
    return key


def collect_files() -> list[Path]:
    """
    Collecte récursivement tous les fichiers cibles.
    - missions/ : parcours récursif (sous-dossiers par mission)
    - reports/, workflows/ : parcours plat
    """
    files = []

    # Missions : récursif (data/missions/<name>/<id>.json)
    missions_dir = DATA_DIR / 'missions'
    if missions_dir.exists():
        for ext in EXTENSIONS:
            files.extend(missions_dir.rglob(f'*{ext}'))
    else:
        print(f"[WARN]  Dossier absent : {missions_dir}")

    # Reports et workflows : plat
    for folder in ['reports', 'workflows']:
        d = DATA_DIR / folder
        if not d.exists():
            print(f"[WARN]  Dossier absent : {d}")
            continue
        for ext in EXTENSIONS:
            files.extend(d.glob(f'*{ext}'))

    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--user',    default='admin')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--delete',  action='store_true')
    args = parser.parse_args()

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Clé utilisée : {args.user}\n")

    b64_key = get_user_key(args.user)
    files   = collect_files()

    if not files:
        print("Aucun fichier à chiffrer.")
        return

    ok = errors = skipped = 0
    for fp in sorted(files):
        enc_path = Path(str(fp) + '.enc')
        if enc_path.exists():
            print(f"[SKIP]  {fp.relative_to(DATA_DIR)}")
            skipped += 1
            continue

        if args.dry_run:
            print(f"[DRY]   {fp.relative_to(DATA_DIR)}  →  {enc_path.name}")
            ok += 1
            continue

        try:
            encrypt_file(str(fp), b64_key)
            print(f"[OK]    {fp.relative_to(DATA_DIR)}  →  {enc_path.name}")
            ok += 1
            if args.delete:
                fp.unlink()
                print(f"[DEL]   {fp.name}")
        except Exception as e:
            print(f"[ERR]   {fp.relative_to(DATA_DIR)} : {e}")
            errors += 1

    print(f"\nChiffrés : {ok}  |  Ignorés : {skipped}  |  Erreurs : {errors}  |  Total : {len(files)}")


if __name__ == '__main__':
    main()