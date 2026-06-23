"""
src/core/cli_session.py
─────────────────────────
Session d'authentification pour le CLI Argos.

SÉCURITÉ : le token JWT et la clé de chiffrement (enc_key) sont conservés
UNIQUEMENT en mémoire du process CLI, jamais écrits sur disque, jamais
journalisés. À la fermeture du CLI (exit/Ctrl+C), tout disparaît.

Le mot de passe n'est jamais stocké, même temporairement au-delà de
l'appel HTTP de login — il transite en mémoire le temps d'un POST
/auth/login puis est oublié (la variable Python sort de portée).
"""

import os

import requests

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:5001")


class CLISession:
    """
    Conteneur de session pour le process CLI. Une seule instance vit
    pendant toute la durée de vie du CLI (module-level singleton via
    get_session()), peuplée par login().
    """

    def __init__(self):
        self.token:      str | None = None
        self.enc_key:    str | None = None
        self.user_id:    str | None = None
        self.username:   str | None = None
        self.api_base:   str = API_BASE

    @property
    def is_authenticated(self) -> bool:
        return bool(self.token and self.enc_key)

    def login(self, username: str, password: str) -> tuple[bool, str]:
        """
        Authentifie auprès de l'API et peuple la session en mémoire.
        Retourne (succès, message).
        """
        try:
            resp = requests.post(
                f"{self.api_base}/auth/login",
                json={"username": username, "password": password},
                timeout=8,
            )
        except requests.exceptions.ConnectionError:
            return False, f"API inaccessible ({self.api_base})"
        except requests.exceptions.RequestException as e:
            return False, f"Erreur réseau : {e}"

        if resp.status_code != 200:
            try:
                error = resp.json().get("error", "Échec de l'authentification")
            except ValueError:
                error = "Échec de l'authentification"
            return False, error

        data = resp.json()
        token   = data.get("token")
        enc_key = data.get("enc_key")
        if not token or not enc_key:
            return False, "Réponse API invalide (token/enc_key manquant)"

        # Décode le sub (user id) depuis le JWT pour affichage/usage —
        # pas de vérification de signature ici, l'API a déjà validé le
        # login ; on lit juste le payload pour récupérer l'id.
        try:
            import base64, json as _json
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
            self.user_id = payload.get("sub")
        except Exception:
            self.user_id = None

        self.token    = token
        self.enc_key  = enc_key
        self.username = username
        return True, f"Connecté en tant que {username}"

    def logout(self) -> None:
        """Efface la session en mémoire — ne fait aucun appel réseau (pas de révocation côté API)."""
        self.token    = None
        self.enc_key  = None
        self.user_id  = None
        self.username = None


# ─── Singleton process-wide ────────────────────────────────────────────────────

_session = CLISession()


def get_session() -> CLISession:
    return _session


def require_session() -> CLISession | None:
    """
    Retourne la session si authentifiée, sinon affiche un message et
    retourne None. Utilisé par les commandes qui exigent un login
    (run, listwf — tout ce qui touche des données chiffrées).
    """
    if not _session.is_authenticated:
        print("[ERROR] Vous devez être connecté pour cette commande. "
              "Relancez le CLI ou tapez 'login'.")
        return None
    return _session