"""
src/WebUI/reports.py
Argos — Routes pour le module Reports.

SÉCURITÉ — réécriture complète :
  - Plus aucune lecture/écriture sur REPORTS_DIR en clair.
  - list_reports() et generate_report() viennent de src.core.report,
    qui passe systématiquement par l'API chiffrée avec owner_id.
  - L'aperçu HTML et le téléchargement PDF déchiffrent en mémoire avec la
    clé du user courant (g.enc_key) au moment de la requête, sans jamais
    écrire le clair sur disque.

S'enregistre directement sur l'instance Flask `app` (pas de Blueprint),
comme dans la version précédente, pour rester compatible avec server.py.
"""

import base64
import os
from flask import request, jsonify, Response, abort, render_template, g

from src.core.report import generate_report, list_reports
from src.WebUI.auth import login_required, API_BASE
from src.variables import MISSIONS_REGISTERY


def _completed_missions_live() -> list[dict]:
    """
    Missions terminées disponibles EN MÉMOIRE process pour cette session
    (celles lancées depuis ce process WebUI et déjà arrivées à leur fin).
    Ne lit plus jamais l'historique sur disque en clair : pour l'historique
    complet, le frontend doit interroger /proxy/files/missions et déchiffrer
    en JS (voir missions.html), ce endpoint ne sert que la sélection rapide
    dans la modale de génération de rapport.
    """
    from datetime import datetime

    def _iso(val):
        if val is None:
            return ""
        if isinstance(val, datetime):
            return val.isoformat()
        return str(val)

    def _workflow_id(val):
        if val is None:
            return ""
        if isinstance(val, str):
            return val
        return getattr(val, "id", str(val))

    return [
        {
            "id":             getattr(m, "id", ""),
            "name":           getattr(m, "name", ""),
            "workflow":       _workflow_id(getattr(m, "workflow", "")),
            "status":         getattr(m, "status", ""),
            "inputs":         getattr(m, "inputs", {}) or {},
            "date_created":   _iso(getattr(m, "date_created", None)),
            "date_completed": _iso(getattr(m, "date_completed", None)),
        }
        for m in MISSIONS_REGISTERY
        if getattr(m, "status", None) == "completed"
    ]


def register_reports_routes(app):
    """Enregistre toutes les routes /reports/* sur l'instance Flask."""

    @app.route("/reports")
    @login_required
    def reports_page():
        """
        Squelette : la liste des rapports est chargée et déchiffrée côté
        navigateur via ArgosDecrypt.listReports() (cohérent avec
        dashboard.html / workflows.html / missions.html).
        La liste des missions complétées (pour la modale "Générer un
        rapport") vient des missions en mémoire de CETTE session.
        """
        from src.variables import (
            MODULES_REGISTERY, WORKFLOWS_REGISTERY,
            WEB_SERVER_HOST, WEB_SERVER_PORT,
            APP_NAME, APP_VERSION, APP_DESCRIPTION,
            APP_AUTHOR, APP_LICENSE, APP_REPOSITORY,
        )
        variables = {
            "WEB_SERVER_HOST": WEB_SERVER_HOST,
            "WEB_SERVER_PORT": WEB_SERVER_PORT,
            "APP_NAME":        APP_NAME,
            "APP_VERSION":     APP_VERSION,
            "APP_DESCRIPTION": APP_DESCRIPTION,
            "APP_AUTHOR":      APP_AUTHOR,
            "APP_LICENSE":     APP_LICENSE,
            "APP_REPOSITORY":  APP_REPOSITORY,
            "MODULES":         MODULES_REGISTERY,
            "WORKFLOWS":       WORKFLOWS_REGISTERY,
        }
        return render_template(
            "reports.html",
            missions=_completed_missions_live(),
            **variables,
        )

    @app.route("/reports/generate", methods=["POST"])
    @login_required
    def reports_generate():
        """
        POST /reports/generate
        Body JSON : { "mission_id": "#MSN-XXXXXXXX", "mission_folder": "..." (optionnel) }

        Récupère la mission :
          1. en mémoire (MISSIONS_REGISTERY) si elle vient d'être lancée
             dans cette session — chemin rapide, pas d'appel réseau ;
          2. sinon, déchiffrée via l'API. mission_folder, transmis par le
             frontend (connu via _mission_folder attaché lors du listing
             dans missions.html/reports.html), permet d'aller chercher
             directement le bon fichier sans scanner tout l'historique.
             Sans mission_folder, on retombe sur un scan complet des
             dossiers visibles par le user courant.

        Génère HTML+PDF, chiffrés avec la clé du user courant avant envoi
        à l'API. owner_id du rapport = user courant (celui qui demande).
        """
        data            = request.get_json(force=True) or {}
        mission_id      = data.get("mission_id", "").strip()
        mission_folder  = data.get("mission_folder", "").strip() or None
        if not mission_id:
            abort(400, description="mission_id manquant")

        mission_obj = next((m for m in MISSIONS_REGISTERY if m.id == mission_id), None)
        if mission_obj:
            from datetime import datetime as _dt
            mission_dict = {
                "id":             mission_obj.id,
                "name":           mission_obj.name,
                "workflow":       getattr(mission_obj.workflow, "id", mission_obj.workflow),
                "status":         mission_obj.status,
                "inputs":         getattr(mission_obj, "inputs", {}) or {},
                "result":         mission_obj.result or {},
                "date_created":   mission_obj.date_created.isoformat() if isinstance(mission_obj.date_created, _dt) else mission_obj.date_created,
                "date_completed": mission_obj.date_completed.isoformat() if isinstance(mission_obj.date_completed, _dt) else mission_obj.date_completed,
            }
        else:
            from src.WebUI.mission_detail import _find_mission_via_api
            mission_dict = _find_mission_via_api(mission_id, folder_hint=mission_folder)
            if mission_dict is None:
                abort(404, description=f"Mission {mission_id} introuvable ou inaccessible")

        try:
            info = generate_report(
                mission_dict,
                api_base=API_BASE,
                token=g.token,
                owner_key=g.enc_key,
            )
        except Exception as e:
            abort(500, description=f"Échec de la génération du rapport : {e}")

        return jsonify({"ok": True, "report": info})

    @app.route("/reports/preview/<report_id>")
    @login_required
    def reports_preview(report_id):
        """
        Déchiffre et retourne le HTML du rapport en mémoire, jamais écrit
        sur disque en clair. Nécessite que le user soit owner ou ait
        rapports:*  (vérifié côté API lors du GET du payload chiffré).
        """
        safe_id  = os.path.basename(report_id)
        filename = f"{safe_id}.html"

        try:
            from src.WebUI.crypto_bridge import fetch_and_decrypt_json
        except ImportError:
            abort(500, description="Module de déchiffrement indisponible")

        html_text = _fetch_and_decrypt_text(filename)
        if html_text is None:
            abort(404)

        return Response(html_text, mimetype="text/html")

    @app.route("/reports/download/<report_id>")
    @login_required
    def reports_download(report_id):
        """
        Déchiffre le PDF (stocké en base64 chiffré) en mémoire et le
        retourne en téléchargement, sans jamais l'écrire sur disque.
        """
        safe_id  = os.path.basename(report_id)
        filename = f"{safe_id}.pdf"

        pdf_b64_text = _fetch_and_decrypt_text(filename)
        if pdf_b64_text is None:
            abort(404)

        try:
            pdf_bytes = base64.b64decode(pdf_b64_text)
        except Exception:
            abort(500, description="Rapport PDF corrompu")

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="argos-report-{safe_id}.pdf"'},
        )

    @app.route("/reports/delete/<report_id>", methods=["DELETE"])
    @login_required
    def reports_delete(report_id):
        """Relais pur vers l'API pour suppression (owner ou rapports:* requis)."""
        import requests
        safe_id = os.path.basename(report_id)
        ok = True
        for ext in ("html", "pdf"):
            try:
                resp = requests.delete(
                    f"{API_BASE}/files/reports/{safe_id}.{ext}",
                    headers={"Authorization": f"Bearer {g.token}"},
                    timeout=10,
                )
                if resp.status_code not in (200, 404):
                    ok = False
            except Exception:
                ok = False
        return jsonify({"ok": ok})


def _fetch_and_decrypt_text(filename: str) -> str | None:
    """
    Récupère le payload chiffré d'un rapport via l'API et le déchiffre
    en mémoire avec la clé résolue par l'API (owner ou emprunt '*').
    Retourne le texte en clair, ou None si introuvable/inaccessible.
    """
    import requests
    from src.crypto_utils import decrypt_bytes

    try:
        resp = requests.get(
            f"{API_BASE}/files/reports/{filename}",
            headers={"Authorization": f"Bearer {g.token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
        plaintext = decrypt_bytes(
            nonce_b64=payload["nonce"],
            ciphertext_b64=payload["ciphertext"],
            b64_key=payload["enc_key"],
        )
        return plaintext.decode("utf-8")
    except Exception as e:
        print(f"[reports] Échec déchiffrement {filename} : {e}")
        return None