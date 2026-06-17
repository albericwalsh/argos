"""
src/WebUI/crypto_bridge.py
────────────────────────────
SÉCURITÉ — lire avant de modifier.

Ce module est la SEULE partie du WebUI Python autorisée à déchiffrer du
contenu en clair. Il est utilisé exclusivement pour reconstruire les
registres en mémoire process (WORKFLOWS_REGISTERY, MISSIONS_REGISTERY)
nécessaires au moteur d'exécution (Workflow.run, Mission.execute,
report_engine), qui ont besoin d'objets Python concrets et non de JSON
chiffré.

Conditions d'utilisation strictes :
  - Appelé UNIQUEMENT juste après un login réussi (la clé vient de la
    réponse fraîche de /auth/login, jamais relue depuis un cookie ou
    un stockage persistant côté serveur).
  - La clé en clair ne doit jamais être journalisée, ni écrite sur disque,
    ni renvoyée dans une réponse HTTP autre que celle du login lui-même.
  - Toute fonction ici déchiffre en mémoire, traite, et oublie — aucune
    mise en cache de texte en clair au-delà de la durée de la requête
    qui déclenche le rechargement des registres.

Ce module utilise les MÊMES primitives AES-GCM que decrypt.js côté
navigateur (cryptography.hazmat AESGCM), garantissant un format
compatible des enveloppes chiffrées entre client et serveur.
"""

import json
import requests

from src.crypto_utils import decrypt_bytes


def fetch_and_decrypt_json(api_base: str, token: str, path: str) -> dict:
    """
    Récupère un payload chiffré depuis l'API (GET) et le déchiffre
    immédiatement en mémoire. Retourne l'objet JSON désérialisé.

    Le payload retourné par l'API contient déjà la clé résolue par le
    serveur (enc_key) — clé du current_user si owner, clé empruntée de
    l'owner si permission '*' — donc cette fonction n'a pas besoin de
    connaître la logique d'attribution, juste d'utiliser la clé fournie.
    """
    resp = requests.get(
        f"{api_base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    payload = resp.json()

    plaintext = decrypt_bytes(
        nonce_b64=payload["nonce"],
        ciphertext_b64=payload["ciphertext"],
        b64_key=payload["enc_key"],
    )
    return json.loads(plaintext.decode("utf-8"))


def encrypt_and_put_json(api_base: str, token: str, path: str, data: dict, original_name: str):
    """
    Chiffre un objet JSON avec la clé du user courant et l'envoie à l'API.
    Utilisé par les opérations serveur qui doivent écrire un fichier
    sans passer par le navigateur (ex: Mission.execute() qui tourne
    dans un thread backend, déclenché depuis une requête authentifiée).

    Nécessite la clé en clair du user courant (transmise explicitement
    par l'appelant, jamais relue depuis un stockage persistant ici).
    """
    from src.crypto_utils import encrypt_bytes

    plaintext = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    # On a besoin de la clé pour chiffrer — récupérée par l'appelant
    # et passée via data.get('_enc_key') serait fragile ; on exige donc
    # un paramètre dédié plutôt que de la cacher dans le payload.
    raise NotImplementedError(
        "Utilisez encrypt_and_put_json_with_key() — la clé doit être "
        "passée explicitement, jamais déduite implicitement."
    )


def encrypt_and_put_json_with_key(
    api_base: str, token: str, path: str, data: dict,
    original_name: str, b64_key: str,
):
    """
    Version explicite : chiffre `data` avec `b64_key` (clé du user
    courant, reçue depuis le contexte de la requête HTTP authentifiée)
    et envoie le résultat à l'API via PUT.
    """
    from src.crypto_utils import encrypt_bytes

    plaintext = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    envelope  = encrypt_bytes(plaintext, b64_key)
    envelope["original_name"] = original_name

    resp = requests.put(
        f"{api_base}{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=envelope,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()