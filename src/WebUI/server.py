import os
import sys

from flask import Flask, render_template
import logging
from flask_cors import CORS
import flask.cli as flask_cli
import threading
from src.variables import  (
    WEB_SERVER_HOST, WEB_SERVER_PORT,
    APP_NAME, APP_VERSION, APP_DESCRIPTION, APP_AUTHOR, APP_LICENSE, APP_REPOSITORY, APP_DIR,
    CORS_ORIGINS, CORS_METHODS, CORS_HEADERS
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
    'APP_REPOSITORY': APP_REPOSITORY
}

@app.route('/')
def index():
    return render_template('index.html', **variables)


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