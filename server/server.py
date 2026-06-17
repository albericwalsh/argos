import flask
from src.auth import login, register, token_required, require_permission
from src.db import init_users, load_users
from src.files import files_bp
from src.auth import token_required, require_permission
from src.admin import admin_bp          # ← nouveau                     # ← nouveau

app = flask.Flask(__name__)

# Initialisation DB au démarrage
with app.app_context():
    init_users()

# ─── Auth ─────────────────────────────────────────────────────────────────────
app.add_url_rule('/auth/register', view_func=register, methods=['POST'])
app.add_url_rule('/auth/login',    view_func=login,    methods=['POST'])

# ─── Fichiers chiffrés ────────────────────────────────────────────────────────
app.register_blueprint(files_bp)                   # ← /files/<category>/...


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

"""
Route GET /users à ajouter dans server.py.
Retourne la liste des users sans les mots de passe ni les clés de chiffrement.
Requiert la permission users:read.
"""

# ─── À ajouter dans server.py ─────────────────────────────────────────────────


@app.route('/users')
@token_required
@require_permission('users', 'read')
def list_users():
    users = load_users()
    # On ne renvoie jamais le mot de passe ni la clé de chiffrement
    safe = [
        {
            'id':              u['id'],
            'username':        u['username'],
            'modules':         u.get('modules', []),
            'rapports_perm':   u.get('rapports_perm', []),
            'missions_perm':   u.get('missions_perm', []),
            'worklows_perm':   u.get('worklows_perm', []),
            'ressources_perm': u.get('ressources_perm', []),
            'users_perm':      u.get('users_perm', []),
        }
        for u in users
    ]
    return flask.jsonify(safe), 200

if __name__ == '__main__':
    app.run(debug=True)