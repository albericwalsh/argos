"""
crypto_utils.py
───────────────
Gestion des clés AES-256-GCM par utilisateur + résolution d'accès par owner.

Chaque user possède une clé symétrique 256 bits stockée dans users.json
sous la clé "encryption_key" (base64url).

Chaque fichier chiffré (mission/rapport/workflow) est chiffré avec la clé
de son OWNER (le user qui l'a créé), et porte un champ "owner_id" en clair
dans son enveloppe (pas dans le contenu chiffré) pour permettre la
résolution d'accès.

Règle d'accès :
  - Si current_user.id == owner_id        → on utilise la clé du current_user
                                              (qui EST la clé de l'owner)
  - Sinon, si current_user a la permission '*' sur la ressource
                                            → on "emprunte" la clé de l'owner
                                              (récupérée dans users.json)
  - Sinon                                  → accès refusé (403)

Le navigateur ne sait jamais laquelle des deux clés il reçoit : il reçoit
toujours "la bonne clé pour déchiffrer ce fichier précis" et déchiffre
en AES-GCM sans connaître l'identité du propriétaire réel.
"""

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ─── Constantes ───────────────────────────────────────────────────────────────

KEY_SIZE_BYTES   = 32   # AES-256
NONCE_SIZE_BYTES = 12   # 96 bits — recommandé pour GCM


# ─── Génération ───────────────────────────────────────────────────────────────

def generate_user_key() -> str:
    """Génère une clé AES-256 aléatoire, retourne en base64url."""
    raw = os.urandom(KEY_SIZE_BYTES)
    return base64.urlsafe_b64encode(raw).decode()


def _pad_b64(s: str) -> str:
    """
    Rajoute le padding '=' manquant avant un urlsafe_b64decode.
    Le JS (decrypt.js) génère du base64url SANS padding ; Python
    base64.urlsafe_b64decode l'exige strictement. Sans cette étape,
    tout decode provenant du navigateur échoue avec "Incorrect padding"
    dès que la longueur de la chaîne n'est pas un multiple de 4.
    """
    return s + '=' * (-len(s) % 4)


def key_from_b64(b64_key: str) -> bytes:
    return base64.urlsafe_b64decode(_pad_b64(b64_key).encode())


# ─── Chiffrement / déchiffrement bas niveau ───────────────────────────────────

def encrypt_bytes(data: bytes, b64_key: str) -> dict:
    """
    Chiffre `data` avec AES-256-GCM.
    Retourne { "nonce": "<base64url>", "ciphertext": "<base64url>" }.
    """
    key   = key_from_b64(b64_key)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, data, None)
    return {
        "nonce":      base64.urlsafe_b64encode(nonce).decode(),
        "ciphertext": base64.urlsafe_b64encode(ct).decode(),
    }


def decrypt_bytes(nonce_b64: str, ciphertext_b64: str, b64_key: str) -> bytes:
    """Déchiffre et vérifie l'authenticité. Lève InvalidTag si la clé est fausse."""
    key    = key_from_b64(b64_key)
    nonce  = base64.urlsafe_b64decode(_pad_b64(nonce_b64).encode())
    ct     = base64.urlsafe_b64decode(_pad_b64(ciphertext_b64).encode())
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


# ─── Résolution d'accès par owner ──────────────────────────────────────────────

def resolve_decryption_key(
    current_user_id: str,
    current_user_key: str,
    owner_id: str,
    has_wildcard_perm: bool,
    users: list[dict],
) -> str | None:
    """
    Détermine quelle clé utiliser pour déchiffrer un fichier appartenant
    à `owner_id`, pour un user `current_user_id` qui dispose de la clé
    `current_user_key` (déjà extraite de son JWT/session).

    - Si current_user_id == owner_id     → retourne current_user_key
    - Si has_wildcard_perm (permission '*' sur la ressource demandée)
                                          → emprunte la clé de owner_id
                                            (recherchée dans `users`)
    - Sinon                              → retourne None (accès refusé)
    """
    if str(current_user_id) == str(owner_id):
        return current_user_key

    if has_wildcard_perm:
        owner = next((u for u in users if str(u["id"]) == str(owner_id)), None)
        if owner:
            return owner.get("encryption_key")
        return None

    return None


def resolve_encryption_key(
    current_user_id: str,
    current_user_key: str,
) -> tuple[str, str]:
    """
    Pour l'écriture (création d'un nouveau fichier) : on chiffre TOUJOURS
    avec la clé de l'auteur de la requête, qui devient l'owner.
    Retourne (owner_id, key_to_use).
    """
    return str(current_user_id), current_user_key