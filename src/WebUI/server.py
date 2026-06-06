from datetime import datetime
import os
import sys

from src.utils import open_file
from flask import Flask, redirect, render_template, request, url_for
import logging
from flask_cors import CORS
import flask.cli as flask_cli
import threading
from src.classes.missions import Mission
from src.variables import  (
    MISSIONS_REGISTERY, MODULES_REGISTERY, WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION, APP_AUTHOR, APP_LICENSE, APP_REPOSITORY, APP_DIR,
    CORS_ORIGINS, CORS_METHODS, CORS_HEADERS, WORKFLOWS_REGISTERY
)

app = Flask(APP_NAME, 
            template_folder=os.path.join(APP_DIR, 'src/WebUI/templates'),
            static_folder=os.path.join(APP_DIR, 'src/WebUI/static'))
    
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

    return render_template('dashboard.html', missions=missions[:5], stats=stats, **variables)


@app.route('/builder')
def builder():
    return render_template('builder.html', **variables)

@app.route('/workflows')
def workflows():
    return render_template('workflows.html', **variables)

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

@app.route('/reports')
def reports():
    return render_template('reports.html', **variables)

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