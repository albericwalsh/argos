from datetime import datetime
import os
import sys

from src.WebUI.reports import register_reports_routes
from src.WebUI.auth import register_auth_routes, login_required
from src.WebUI.proxy import proxy_bp
from src.WebUI.admin import admin_bp as webui_admin_bp
from src.WebUI.account import account_bp
from src.WebUI.modules import modules_bp
from flask import Flask, redirect, render_template, request, url_for, g, jsonify
import logging
from flask_cors import CORS
import threading
from src.classes.missions import Mission
from src.variables import (
    MISSIONS_REGISTERY, MODULES_REGISTERY, WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION, APP_AUTHOR, APP_LICENSE, APP_REPOSITORY, APP_DIR,
    CORS_ORIGINS, CORS_METHODS, CORS_HEADERS, WORKFLOWS_REGISTERY
)
from src.WebUI.mission_detail import bp as mission_detail_bp
from src.WebUI.resources import bp as resources_bp

app = Flask(APP_NAME,
            template_folder=os.path.join(APP_DIR, 'src/WebUI/templates'),
            static_folder=os.path.join(APP_DIR, 'src/WebUI/static'))

app.secret_key = os.environ.get("WEBUI_SECRET_KEY", "dev-webui-secret-change-in-prod")

CORS(app, resources={
    r"/*": {
        "origins": CORS_ORIGINS,
        "methods": CORS_METHODS,
        "allow_headers": CORS_HEADERS,
    }
})

# ── Enregistrement des blueprints et routes ───────────────────────────────────
register_auth_routes(app)
register_reports_routes(app)
app.register_blueprint(mission_detail_bp)
app.register_blueprint(resources_bp)
app.register_blueprint(proxy_bp)
app.register_blueprint(webui_admin_bp)
app.register_blueprint(account_bp)
app.register_blueprint(modules_bp)

variables = {
    'WEB_SERVER_HOST': WEB_SERVER_HOST,
    'WEB_SERVER_PORT': WEB_SERVER_PORT,
    'APP_NAME':        APP_NAME,
    'APP_VERSION':     APP_VERSION,
    'APP_DESCRIPTION': APP_DESCRIPTION,
    'APP_AUTHOR':      APP_AUTHOR,
    'APP_LICENSE':     APP_LICENSE,
    'APP_REPOSITORY':  APP_REPOSITORY,
    'MODULES':         MODULES_REGISTERY,
    'WORKFLOWS':       WORKFLOWS_REGISTERY,
}

@app.template_global()
def module_style(name):
    h = abs(hash(name)) % 360
    return f"background:hsl({h},55%,60%,0.12);color:hsl({h},70%,65%)"

@app.context_processor
def inject_globals():
    import base64, json as _json
    is_admin = False
    try:
        from src.WebUI.auth import get_token
        token = get_token()
        if token:
            payload_b64 = token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
            users_perm = payload.get("permissions", {}).get("users", [])
            is_admin = bool(users_perm)
    except Exception:
        pass
    return {"is_admin": is_admin}


# ══════════════════════════════════════════════════════════════════════════════
#  SÉCURITÉ — RAPPEL
#  Le WebUI Python ne lit/écrit JAMAIS data/missions ou data/workflows en clair.
#  Tout le contenu chiffré transite via /proxy/files/* et est déchiffré
#  uniquement dans le navigateur (decrypt.js), avec la clé du user connecté.
#  Les routes ci-dessous ne rendent que des SQUELETTES HTML ; le contenu
#  (missions, workflows) est hydraté côté client en JS après déchiffrement.
#  Seules les missions EN COURS (MISSIONS_REGISTERY, en mémoire process,
#  non persistées chiffrées) sont injectées directement — elles ne sont pas
#  considérées sensibles au même titre que l'historique chiffré sur disque.
# ══════════════════════════════════════════════════════════════════════════════

def _live_missions_json():
    """Sérialise les missions en cours (mémoire) pour hydratation JS initiale."""
    return [
        {
            "id":             m.id,
            "name":           m.name,
            "workflow":       m.workflow.id,
            "status":         m.status,
            "inputs":         {},
            "date_created":   m.date_created.isoformat(),
            "date_completed": m.date_completed.isoformat() if m.date_completed else None,
        }
        for m in MISSIONS_REGISTERY
    ]


@app.route('/')
@login_required
def index():
    """
    Squelette du dashboard. Le détail des missions terminées et des
    rapports est chargé en JS via ArgosDecrypt.listMissions() / listReports()
    puis déchiffré en mémoire navigateur.
    """
    live_missions = _live_missions_json()
    stats = {
        'missions_ok':      0,   # recalculé en JS une fois l'historique déchiffré
        'missions_running': sum(1 for m in MISSIONS_REGISTERY if m.status == 'running'),
        'missions_error':   0,
    }
    return render_template(
        'dashboard.html',
        live_missions=live_missions,
        live_missions_json=live_missions,
        stats=stats,
        **variables,
    )


@app.route('/builder')
@login_required
def builder():
    """
    Squelette du builder. Si ?load=<id> est fourni, le JS récupère et
    déchiffre le workflow via ArgosDecrypt.fetchWorkflowJSON(load_id).
    """
    import json as _json
    modules_list = [
        {
            "id":          m.id,
            "name":        m.name,
            "category":    m.category,
            "description": m.description,
            "entry_arg":   m.entry_arg,
            "parameters":  getattr(m, 'parameters', []),
        }
        for m in MODULES_REGISTERY
    ]
    modules_json = _json.dumps(modules_list, ensure_ascii=False)
    load_id = request.args.get('load', '')

    return render_template('builder.html', load_id=load_id,
                           modules_json=modules_json, **variables)


@app.route('/workflows')
@login_required
def workflows():
    """Squelette. Le JS charge et déchiffre la liste via ArgosDecrypt.listWorkflows()."""
    return render_template('workflows.html', **variables)


@app.route('/workflows/save', methods=['POST'])
@login_required
def workflows_save():
    """
    Relais pur : le JS a déjà chiffré le workflow côté client
    ({ nonce, ciphertext, original_name }). Ce serveur ne fait que
    transmettre à l'API — il ne voit jamais le clair.
    Body attendu : { "filename": "<id>.json", "payload": {nonce, ciphertext, original_name} }
    """
    import requests
    from src.WebUI.auth import API_BASE

    data     = request.get_json(force=True) or {}
    filename = data.get('filename', '').strip()
    payload  = data.get('payload')

    if not filename or not payload:
        return jsonify({'ok': False, 'error': 'filename et payload requis'}), 400

    safe_name = os.path.basename(filename)
    try:
        resp = requests.put(
            f"{API_BASE}/files/workflows/{safe_name}",
            headers={"Authorization": f"Bearer {g.token}"},
            json=payload,
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({'ok': False, 'error': 'API inaccessible'}), 503

    if resp.status_code not in (200, 201):
        return jsonify({'ok': False, 'error': resp.json().get('error', 'Erreur API')}), resp.status_code

    return jsonify({'ok': True, 'id': safe_name.replace('.json', '')}), 200


@app.route('/workflows/sync', methods=['POST'])
@login_required
def workflows_sync():
    """
    Appelé par builder.html juste APRÈS un PUT chiffré réussi vers
    /proxy/files/workflows/<filename> (via ArgosDecrypt.saveWorkflow()).

    Le navigateur a déjà le JSON en clair du workflow à ce moment précis
    (avant chiffrement) ; il le transmet ici pour que le serveur Python
    mette à jour WORKFLOWS_REGISTERY en mémoire SANS avoir besoin de
    redéchiffrer quoi que ce soit — ce n'est pas une fuite de sécurité
    supplémentaire : c'est le même clair que celui qui vient d'être
    chiffré et envoyé une ligne plus haut côté JS, simplement dupliqué
    vers cet endpoint pour la synchro du registre serveur.

    Body JSON : { "workflow": {...}, "filename": "<id>.json" }
    """
    data     = request.get_json(force=True) or {}
    wf_dict  = data.get('workflow')
    filename = data.get('filename', '')

    if not wf_dict or not wf_dict.get('id'):
        return jsonify({'ok': False, 'error': 'workflow (avec id) requis'}), 400

    from src.core.workflow_runner import upsert_workflow_in_registry
    try:
        wf = upsert_workflow_in_registry(wf_dict, source_name=filename)
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

    return jsonify({'ok': True, 'id': wf.id}), 200


@app.route('/workflows/delete/<workflow_id>', methods=['DELETE'])
@login_required
def workflows_delete(workflow_id):
    """
    Relais vers l'API pour suppression du fichier chiffré, PUIS retire
    également le workflow de WORKFLOWS_REGISTERY (mémoire serveur) pour
    qu'il disparaisse immédiatement de /run/<id> sans reconnexion.
    """
    import requests
    from src.WebUI.auth import API_BASE
    from src.core.workflow_runner import remove_workflow_from_registry

    safe_id = os.path.basename(workflow_id)
    try:
        resp = requests.delete(
            f"{API_BASE}/files/workflows/{safe_id}.json",
            headers={"Authorization": f"Bearer {g.token}"},
            timeout=10,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({'ok': False, 'error': 'API inaccessible'}), 503

    if resp.status_code not in (200, 204):
        return jsonify({'ok': False, 'error': resp.json().get('error', 'Erreur API')}), resp.status_code

    remove_workflow_from_registry(safe_id)
    return jsonify({'ok': True}), 200


@app.route('/missions')
@login_required
def missions():
    """
    Squelette. Les missions en cours (live) sont injectées immédiatement ;
    l'historique chiffré est chargé et déchiffré en JS via
    ArgosDecrypt.listMissions() + fetchMissionJSON() pour chaque fichier.
    """
    live_missions = _live_missions_json()
    return render_template('missions.html', live_missions_json=live_missions, **variables)


# Route /modules retirée — remplacée par le blueprint modules_bp
# (src/WebUI/modules.py), qui gère aussi l'upload/suppression de modules.


@app.route('/run/<workflow_id>', methods=['GET', 'POST'])
@login_required
def run_workflow(workflow_id):
    workflow = next((w for w in WORKFLOWS_REGISTERY if w.id == workflow_id), None)
    if not workflow:
        return "Workflow not found", 404

    if request.method == 'POST':
        from src.WebUI.auth import API_BASE
        import base64, json as _json

        inputs       = {key: request.form.get(key, '') for key in workflow.entry_args.keys()}
        mission_name = request.form.get('mission_name', workflow.name)

        # Récupère l'id du user courant depuis le JWT (g.token, posé par @login_required)
        payload_b64 = g.token.split('.')[1]
        payload_b64 += '=' * (4 - len(payload_b64) % 4)
        payload     = _json.loads(base64.urlsafe_b64decode(payload_b64))
        owner_id    = payload.get('sub')

        mission = Mission(
            name=mission_name,
            workflow=workflow,
            owner_id=owner_id,
            owner_key=g.enc_key,
            api_base=API_BASE,
            api_token=g.token,
        )
        MISSIONS_REGISTERY.append(mission)
        thread = threading.Thread(target=mission.execute, args=(inputs,), daemon=True)
        thread.start()
        return redirect(url_for('missions'))

    return render_template('run.html', workflow=workflow, **variables)


# ══════════════════════════════════════════════════════════════════════════════
#  GESTION D'ERREURS GLOBALE
#  Toutes les erreurs HTTP (401/403/404/500/503) sont rendues via un
#  template unique error.html plutôt que la page Werkzeug par défaut.
# ══════════════════════════════════════════════════════════════════════════════

def _render_error(code: int, message: str = None, detail: str = None):
    return render_template('error.html', code=code, message=message, detail=detail, **variables), code


@app.errorhandler(401)
def handle_401(e):
    # 401 redirige directement vers le login plutôt que d'afficher une page,
    # cohérent avec le comportement existant de @login_required.
    next_path = request.path if request.method == 'GET' else None
    if next_path:
        return redirect(url_for('login_page', next=next_path))
    return _render_error(401, getattr(e, 'description', None))


@app.errorhandler(403)
def handle_403(e):
    return _render_error(403, getattr(e, 'description', None))


@app.errorhandler(404)
def handle_404(e):
    return _render_error(404, getattr(e, 'description', None))


@app.errorhandler(500)
def handle_500(e):
    return _render_error(500, detail=str(e))


@app.errorhandler(503)
def handle_503(e):
    return _render_error(503, getattr(e, 'description', None))


# ══════════════════════════════════════════════════════════════════════════════
#  DÉMARRAGE
# ══════════════════════════════════════════════════════════════════════════════

def start_web_server():
    global app, WEB_SERVER_HOST, WEB_SERVER_PORT

    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    devnull    = open(os.devnull, 'w')
    old_stdout = sys.stdout
    sys.stdout = devnull

    thread = threading.Thread(
        target=lambda: app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, use_reloader=False),
        daemon=True
    )
    thread.start()
    thread.join(timeout=0.5)

    sys.stdout = old_stdout
    devnull.close()

    print(f"[WebUI] Server started on http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    return True