#!/usr/bin/env python3
"""
scripts/generate_keys.py
─────────────────────────
Génère une clé AES-256 pour chaque utilisateur qui n'en possède pas encore,
et la persiste dans data/users.json.

À exécuter UNE seule fois après l'installation, avant encrypt_files.py.

Usage :
    python scripts/generate_keys.py
    python scripts/generate_keys.py --dry-run
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.crypto_utils import generate_user_key
from src.db import load_users, save_users


def main():
    parser = argparse.ArgumentParser(description='Génère les clés AES par utilisateur')
    parser.add_argument('--dry-run', action='store_true', help='Affiche sans écrire')
    args = parser.parse_args()

    users   = load_users()
    updated = 0

    for user in users:
        if user.get('encryption_key'):
            print(f"[SKIP]  {user['username']} — clé déjà présente")
            continue

        key = generate_user_key()
        if args.dry_run:
            print(f"[DRY]   {user['username']} — clé générée (non sauvegardée) : {key[:16]}…")
        else:
            user['encryption_key'] = key
            print(f"[OK]    {user['username']} — clé générée et sauvegardée")
        updated += 1

    if not args.dry_run and updated:
        save_users(users)
        print(f"\n{updated} clé(s) sauvegardée(s) dans users.json")
    elif args.dry_run:
        print(f"\n(dry-run : {updated} clé(s) auraient été générées)")
    else:
        print("\nAucune clé à générer.")


if __name__ == '__main__':
    main()