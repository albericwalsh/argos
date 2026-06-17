"""
src/WebUI/auth.py
─────────────────
Gestion de l'authentification dans le WebUI Argos.

Flux :
  1. L'utilisateur poste ses credentials sur POST /login
  2. Le WebUI les transmet à l'API (:5001/auth/login)
  3. L'API retourne { token, enc_key }
  4. Le WebUI stocke le JWT dans un cookie HttpOnly + Secure
     et l'enc_key dans un cookie HttpOnly + Secure séparé
     (les deux sont inaccessibles depuis JS — le proxy les lit côté serveur)
  5. Chaque page protégée valide le cookie via @login_required
  6. Le template reçoit enc_key pour que decrypt.js puisse déchiffrer
"""

import os
import json
from functools import wraps

import requests
from flask import (
    request, redirect, url_for, make_response,
    render_template, flash, g
)

# URL de l'API — overridable via variable d'environnement
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:5001")

# Noms des cookies
COOKIE_TOKEN   = "argos_token"
COOKIE_ENC_KEY = "argos_enc_key"

# Durée de vie du cookie (secondes) — doit correspondre à TOKEN_EXPIRY_HOURS de l'API
COOKIE_MAX_AGE = int(os.environ.get("TOKEN_EXPIRY_HOURS", 24)) * 3600

# True en prod (HTTPS), False en dev (HTTP)
COOKIE_SECURE = os.environ.get("FLASK_ENV", "development") == "production"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_token() -> str | None:
    """Lit le JWT depuis le cookie de la requête courante."""
    return request.cookies.get(COOKIE_TOKEN)

def get_enc_key() -> str | None:
    """Lit la clé de chiffrement depuis le cookie."""
    return request.cookies.get(COOKIE_ENC_KEY)

def _set_auth_cookies(response, token: str, enc_key: str):
    """Pose les deux cookies sécurisés sur la réponse Flask."""
    opts = dict(
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="Lax",
        path="/",
    )
    response.set_cookie(COOKIE_TOKEN,   token,   **opts)
    response.set_cookie(COOKIE_ENC_KEY, enc_key, **opts)

def _clear_auth_cookies(response):
    """Supprime les cookies d'auth."""
    response.delete_cookie(COOKIE_TOKEN,   path="/")
    response.delete_cookie(COOKIE_ENC_KEY, path="/")


# ─── Décorateur ───────────────────────────────────────────────────────────────

def login_required(f):
    """
    Protège une route WebUI.
    Si le cookie JWT est absent → redirige vers /login.
    Sinon injecte g.token et g.enc_key pour les vues et templates.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token   = get_token()
        enc_key = get_enc_key()
        if not token or not enc_key:
            return redirect(url_for("login_page", next=request.path))
        g.token   = token
        g.enc_key = enc_key
        return f(*args, **kwargs)
    return decorated


# ─── Routes ───────────────────────────────────────────────────────────────────

def register_auth_routes(app):
    """Enregistre GET /login, POST /login, GET /logout sur l'app Flask."""

    @app.route("/login", methods=["GET"])
    def login_page():
        # Si déjà connecté, redirige vers /
        if get_token() and get_enc_key():
            return redirect(url_for("index"))
        error = request.args.get("error")
        return render_template("login.html", error=error)

    @app.route("/login", methods=["POST"])
    def login_submit():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return redirect(url_for("login_page", error="Champs requis"))

        # Transmet à l'API
        try:
            resp = requests.post(
                f"{API_BASE}/auth/login",
                json={"username": username, "password": password},
                timeout=5,
            )
        except requests.exceptions.ConnectionError:
            return redirect(url_for("login_page", error="API inaccessible"))

        if resp.status_code != 200:
            data = resp.json()
            return redirect(url_for("login_page",
                                    error=data.get("error", "Identifiants invalides")))

        data    = resp.json()
        token   = data.get("token")
        enc_key = data.get("enc_key")

        if not token or not enc_key:
            return redirect(url_for("login_page", error="Réponse API invalide"))

        # ── Chargement des registres pour cette session, post-login ────────
        # Workflows/missions ne sont JAMAIS chargés tant qu'aucun user n'est
        # authentifié. On les recharge ici avec la clé fraîche reçue de l'API,
        # jamais persistée au-delà de cette requête.
        try:
            from src.core.workflow_runner import load_workflows_for_user
            load_workflows_for_user(API_BASE, token)
        except Exception as e:
            print(f"[auth] Échec du chargement des workflows post-login : {e}")

        # Redirige vers la destination demandée ou /
        next_url = request.args.get("next") or url_for("index")
        response = make_response(redirect(next_url))
        _set_auth_cookies(response, token, enc_key)
        return response

    @app.route("/logout")
    def logout():
        response = make_response(redirect(url_for("login_page")))
        _clear_auth_cookies(response)
        return response

    @app.route("/auth/register", methods=["POST"])
    def auth_register():
        """
        Proxy AJAX vers POST :5001/auth/register.
        Appelé par le JS du formulaire login (onglet Register).
        Retourne JSON directement (pas de redirect).
        """
        from flask import Response
        body = request.get_json(silent=True) or {}
        try:
            resp = requests.post(
                f"{API_BASE}/auth/register",
                json=body,
                timeout=5,
            )
            return Response(
                resp.content,
                status=resp.status_code,
                content_type="application/json",
            )
        except requests.exceptions.ConnectionError:
            return jsonify({"error": "API inaccessible"}), 503