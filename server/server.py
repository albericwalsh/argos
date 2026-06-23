import flask
from src.auth import (
    login, register, token_required, require_permission,
    get_my_profile, update_my_profile, update_my_password,
)
from src.db import init_users
from src.files import files_bp
from src.admin import admin_bp

app = flask.Flask(__name__)

# Initialisation DB au démarrage
with app.app_context():
    init_users()

# ─── Auth ─────────────────────────────────────────────────────────────────────
app.add_url_rule('/auth/register', view_func=register, methods=['POST'])
app.add_url_rule('/auth/login',    view_func=login,    methods=['POST'])

# ─── Profil personnel (tout user connecté, sur SON propre compte) ────────────
app.add_url_rule('/auth/me',          view_func=get_my_profile,    methods=['GET'])
app.add_url_rule('/auth/me',          view_func=update_my_profile, methods=['PATCH'])
app.add_url_rule('/auth/me/password', view_func=update_my_password, methods=['POST'])

# ─── Fichiers chiffrés ────────────────────────────────────────────────────────
app.register_blueprint(files_bp)

# ─── Admin ────────────────────────────────────────────────────────────────────
app.register_blueprint(admin_bp)

# ─── Routes protégées ─────────────────────────────────────────────────────────
@app.route('/me')
@token_required
def me():
    return flask.jsonify(flask.request.current_user)

@app.route('/')
def index():
    return "Hello, World!"


if __name__ == '__main__':
    app.run(debug=True)