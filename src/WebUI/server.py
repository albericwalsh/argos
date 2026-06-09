from datetime import datetime
import os
import sys

# ✅ Ajouter cet import
from src.WebUI.reports import register_reports_routes, REPORTS_DIR
from src.core.report import list_reports
from src.utils import open_file
from flask import Flask, redirect, render_template, request, url_for
import logging
from flask_cors import CORS
import threading
from src.classes.missions import Mission
from src.variables import  (
    MISSIONS_REGISTERY, MODULES_REGISTERY, WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION, APP_AUTHOR, APP_LICENSE, APP_REPOSITORY, APP_DIR,
    CORS_ORIGINS, CORS_METHODS, CORS_HEADERS, WORKFLOWS_REGISTERY
)
from src.WebUI.mission_detail import bp as mission_detail_bp
from src.WebUI.resources import bp as resources_bp

app = Flask(APP_NAME, 
            template_folder=os.path.join(APP_DIR, 'src/WebUI/templates'),
            static_folder=os.path.join(APP_DIR, 'src/WebUI/static'))

# ✅ Ajouter cette ligne après la création de app (après le bloc CORS)
register_reports_routes(app)
app.register_blueprint(mission_detail_bp)
app.register_blueprint(resources_bp)

# CORS configuration
CORS(app, resources={
    r"/*": {
        "origins": CORS_ORIGINS,
        "methods": CORS_METHODS,
        "allow_headers": CORS_HEADERS,
    }
})
variables = {
    'WEB_SERVER_HOST': WEB_SERVER_HOST,
    'WEB_SERVER_PORT': WEB_SERVER_PORT,
    'APP_NAME': APP_NAME,
    'APP_VERSION': APP_VERSION,
    'APP_DESCRIPTION': APP_DESCRIPTION,
    'APP_AUTHOR': APP_AUTHOR,
    'APP_LICENSE': APP_LICENSE,
    'APP_REPOSITORY': APP_REPOSITORY,
    'MODULES': MODULES_REGISTERY,
    'WORKFLOWS': WORKFLOWS_REGISTERY
}

@app.template_global()
def module_style(name):
    h = abs(hash(name)) % 360
    return f"background:hsl({h},55%,60%,0.12);color:hsl({h},70%,65%)"

@app.route('/')
def index():
    missions_dir = os.path.join(APP_DIR, 'data/missions')
    all_missions = []
    if os.path.exists(missions_dir):
        for folder in sorted(os.listdir(missions_dir), reverse=True):
            folder_path = os.path.join(missions_dir, folder)
            if os.path.isdir(folder_path):
                for file in os.listdir(folder_path):
                    if file.endswith('.json'):
                        all_missions.append(open_file(os.path.join(folder_path, file)))

    # Fusionne avec les missions en mémoire (en cours)
    live_ids = {m.id for m in MISSIONS_REGISTERY}
    live = [{"id": m.id, "name": m.name, "workflow": m.workflow.id,
             "status": m.status, "inputs": {},
             "date_created": m.date_created.isoformat(),
             "date_completed": None} for m in MISSIONS_REGISTERY]
    history = [m for m in all_missions if m.get('id') not in live_ids]
    missions = live + history

    # Calcul durée
    for m in missions:
        if m.get('date_completed') and m.get('date_created'):
            d1 = datetime.fromisoformat(m['date_created'])
            d2 = datetime.fromisoformat(m['date_completed'])
            delta = int((d2 - d1).total_seconds())
            m['duration'] = f"{delta // 60}m {delta % 60}s"
        else:
            m['duration'] = '—'

    stats = {
        'missions_ok': sum(1 for m in missions if m.get('status') == 'completed'),
        'missions_running': sum(1 for m in MISSIONS_REGISTERY if m.status == 'running'),
        'missions_error': sum(1 for m in missions if m.get('status') == 'failed'),
    }

    reports = list_reports(REPORTS_DIR)

    return render_template('dashboard.html', missions=missions[:5], stats=stats, reports=reports[:5], **variables)


@app.route('/builder')
def builder():
    import json as _json
    # Sérialise les modules en dicts pour le template JS
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

    # Chargement optionnel d'un workflow existant pour édition
    load_id = request.args.get('load')
    load_wf = None
    if load_id:
        wf_path = os.path.join(APP_DIR, 'data', 'workflows', f'{load_id}.json')
        if os.path.exists(wf_path):
            with open(wf_path, encoding='utf-8') as f:
                load_wf = _json.load(f)

    return render_template('builder.html', load_wf=load_wf, modules_json=modules_json, **variables)

@app.route('/workflows')
def workflows():
    return render_template('workflows.html', **variables)

@app.route('/workflows/save', methods=['POST'])
def workflows_save():
    import json as _json
    data = request.get_json(force=True) or {}
    wf_id = data.get('id', '').strip()
    if not wf_id:
        return _json.dumps({'ok': False, 'error': 'id manquant'}), 400, {'Content-Type': 'application/json'}

    wf_dir = os.path.join(APP_DIR, 'data', 'workflows')
    os.makedirs(wf_dir, exist_ok=True)
    wf_path = os.path.join(wf_dir, f'{wf_id}.json')

    with open(wf_path, 'w', encoding='utf-8') as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)

    # Reload into WORKFLOWS_REGISTERY
    from src.classes.workflows import Workflow
    existing = next((i for i, w in enumerate(WORKFLOWS_REGISTERY) if w.id == wf_id), None)
    try:
        new_wf = Workflow(wf_path)
        if existing is not None:
            WORKFLOWS_REGISTERY[existing] = new_wf
        else:
            WORKFLOWS_REGISTERY.append(new_wf)
    except Exception as e:
        return _json.dumps({'ok': False, 'error': str(e)}), 500, {'Content-Type': 'application/json'}

    return _json.dumps({'ok': True, 'id': wf_id}), 200, {'Content-Type': 'application/json'}

@app.route('/workflows/delete/<workflow_id>', methods=['DELETE'])
def workflows_delete(workflow_id):
    import json as _json
    safe_id = os.path.basename(workflow_id)
    wf_path = os.path.join(APP_DIR, 'data', 'workflows', f'{safe_id}.json')
    if os.path.exists(wf_path):
        os.remove(wf_path)
    # Remove from registry
    idx = next((i for i, w in enumerate(WORKFLOWS_REGISTERY) if w.id == safe_id), None)
    if idx is not None:
        WORKFLOWS_REGISTERY.pop(idx)
    return _json.dumps({'ok': True}), 200, {'Content-Type': 'application/json'}

@app.route('/missions')
def missions():
    # Missions en cours (en mémoire)
    live = [
        {
            "id": m.id,
            "name": m.name,
            "workflow": m.workflow.id,
            "status": m.status,
            "date_created": m.date_created.isoformat(),
            "date_completed": m.date_completed.isoformat() if m.date_completed else None,
            "duration": None
        }
        for m in MISSIONS_REGISTERY
    ]
    live_ids = {m["id"] for m in live}

    # Historique fichiers (évite les doublons avec live)
    missions_dir = os.path.join(APP_DIR, 'data/missions')
    history = []
    if os.path.exists(missions_dir):
        for folder in sorted(os.listdir(missions_dir), reverse=True):
            folder_path = os.path.join(missions_dir, folder)
            if os.path.isdir(folder_path):
                for file in os.listdir(folder_path):
                    if file.endswith('.json'):
                        data = open_file(os.path.join(folder_path, file))
                        if data.get('id') not in live_ids:
                            history.append(data)

    missions_list = live + history

    # Calcul durée
    for m in missions_list:
        if m.get('date_completed') and m.get('date_created'):
            d1 = datetime.fromisoformat(m['date_created'])
            d2 = datetime.fromisoformat(m['date_completed'])
            delta = int((d2 - d1).total_seconds())
            m['duration'] = f"{delta // 60}m {delta % 60}s"
        else:
            m['duration'] = '—'

    return render_template('missions.html', missions=missions_list, **variables)

@app.route('/modules')
def modules():
    return render_template('modules.html', **variables)

@app.route('/run/<workflow_id>', methods=['GET', 'POST'])
def run_workflow(workflow_id):
    workflow = next((w for w in WORKFLOWS_REGISTERY if w.id == workflow_id), None)
    if not workflow:
        return "Workflow not found", 404

    if request.method == 'POST':
        inputs = {key: request.form.get(key, '') for key in workflow.entry_args.keys()}
        mission_name = request.form.get('mission_name', workflow.name)
        
        mission = Mission(name=mission_name, workflow=workflow)
        MISSIONS_REGISTERY.append(mission)

        # Lance en arrière-plan et redirige immédiatement
        thread = threading.Thread(target=mission.execute, args=(inputs,), daemon=True)
        thread.start()

        return redirect(url_for('missions'))

    return render_template('run.html', workflow=workflow, **variables)

def start_web_server():
    global app, WEB_SERVER_HOST, WEB_SERVER_PORT

    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    devnull = open(os.devnull, 'w')
    old_stdout = sys.stdout
    sys.stdout = devnull

    thread = threading.Thread(
        target=lambda: app.run(host=WEB_SERVER_HOST, port=WEB_SERVER_PORT, use_reloader=False),
        daemon=True
    )
    thread.start()
    thread.join(timeout=0.5)

    sys.stdout = old_stdout  # <-- bien restauré avant le return
    devnull.close()

    print(f"[WebUI] Server started on http://{WEB_SERVER_HOST}:{WEB_SERVER_PORT}")
    return True