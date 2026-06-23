"""
src/WebUI/modules.py
─────────────────────
Page /modules — installation de modules via upload de fichier .zip,
suppression, et vérification de version par rapport à un repository
distant (URL vers un module.json de référence, ex: GitHub raw).

SÉCURITÉ — extraction de zip :
  L'extraction d'archives zip est une source classique de path traversal
  (entrées "../../etc/passwd" dans le zip). Toute entrée est validée pour
  rester strictement contenue dans le dossier cible avant écriture —
  voir _safe_extract().

Les modules ne sont PAS chiffrés (ce sont du code et de la configuration
d'application, pas des données utilisateur), cohérent avec le traitement
déjà appliqué à data/modules dans report.py.
"""

import os
import re
import shutil
import zipfile
import tempfile

import requests
from flask import Blueprint, render_template, jsonify, request, g

from src.WebUI.auth import login_required
from src.variables import APP_DIR, MODULES_REGISTERY, WORKFLOWS_REGISTERY
from src.core.module_loader import reload_modules_registery
from functools import wraps

modules_bp = Blueprint("modules_ui", __name__, url_prefix="/modules")

MODULES_DIR = os.path.join(APP_DIR, "data", "modules")
ALLOWED_ID_PATTERN = re.compile(r"^[a-z0-9_\-]+$")


def _current_has_modules_write() -> bool:
    """
    Vérifie la permission 'modules' du JWT courant (g.token, posé par
    @login_required, qui doit donc être appliqué avant ce décorateur).
    Le schéma existant pour cette ressource est binaire ([] ou ['*'])
    plutôt que read/write séparés (cohérent avec users.json :
    "modules": ["*"] pour l'admin), donc toute présence de '*' autorise
    l'installation/suppression.
    """
    import base64, json as _json
    token = getattr(g, "token", None)
    if not token:
        return False
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_b64))
        return "*" in payload.get("permissions", {}).get("modules", [])
    except Exception:
        return False


def require_modules_write(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _current_has_modules_write():
            return jsonify({"error": "Permission refusée : modules (accès admin requis)"}), 403
        return f(*args, **kwargs)
    return decorated


def _variables():
    from src.variables import (
        WEB_SERVER_HOST, WEB_SERVER_PORT,
        APP_NAME, APP_VERSION, APP_DESCRIPTION,
        APP_AUTHOR, APP_LICENSE, APP_REPOSITORY,
    )
    return {
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


# ─── Sécurité extraction zip ────────────────────────────────────────────────────

def _safe_extract(zf: zipfile.ZipFile, dest_dir: str):
    """
    Extrait un zip dans dest_dir en refusant toute entrée qui sortirait
    de ce dossier (path traversal via "../", chemins absolus, etc.).
    Lève ValueError si une entrée malveillante est détectée.
    """
    dest_dir_real = os.path.realpath(dest_dir)

    for member in zf.namelist():
        # Rejette les chemins absolus ou les remontées explicites
        if member.startswith("/") or member.startswith("\\"):
            raise ValueError(f"Entrée zip invalide (chemin absolu) : {member}")

        target_path = os.path.realpath(os.path.join(dest_dir, member))
        if not target_path.startswith(dest_dir_real + os.sep) and target_path != dest_dir_real:
            raise ValueError(f"Entrée zip invalide (path traversal détecté) : {member}")

    zf.extractall(dest_dir)


def _find_module_json_root(extracted_dir: str) -> str | None:
    """
    Le zip peut soit contenir module.json directement à la racine, soit
    dans un sous-dossier unique (cas fréquent : "mon-module/module.json"
    quand on zippe un dossier directement). Retourne le dossier contenant
    réellement module.json, ou None si introuvable.
    """
    direct = os.path.join(extracted_dir, "module.json")
    if os.path.exists(direct):
        return extracted_dir

    entries = [e for e in os.listdir(extracted_dir) if not e.startswith("__MACOSX")]
    if len(entries) == 1:
        candidate = os.path.join(extracted_dir, entries[0])
        if os.path.isdir(candidate) and os.path.exists(os.path.join(candidate, "module.json")):
            return candidate

    return None


# ─── Routes ───────────────────────────────────────────────────────────────────

@modules_bp.route("")
@login_required
def modules_page():
    return render_template("modules.html", **_variables())


@modules_bp.route("/install", methods=["POST"])
@login_required
@require_modules_write
def install_module():
    """
    POST /modules/install
    Form-data : file=<archive.zip>
    Extrait l'archive dans un dossier temporaire, valide la présence de
    module.json et entry.py, puis déplace le tout dans
    data/modules/<id>/ (id pris depuis module.json, pas depuis le nom
    du fichier uploadé — évite toute confusion/collision de nommage).
    """
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu (champ 'file' attendu)"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename or not uploaded.filename.lower().endswith(".zip"):
        return jsonify({"error": "Seuls les fichiers .zip sont acceptés"}), 400

    with tempfile.TemporaryDirectory() as tmp_dir:
        zip_path = os.path.join(tmp_dir, "upload.zip")
        uploaded.save(zip_path)

        try:
            with zipfile.ZipFile(zip_path) as zf:
                extract_dir = os.path.join(tmp_dir, "extracted")
                os.makedirs(extract_dir, exist_ok=True)
                _safe_extract(zf, extract_dir)
        except zipfile.BadZipFile:
            return jsonify({"error": "Fichier zip invalide ou corrompu"}), 400
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        module_root = _find_module_json_root(extract_dir)
        if module_root is None:
            return jsonify({"error": "module.json introuvable dans l'archive "
                                      "(attendu à la racine ou dans un unique sous-dossier)"}), 400

        import json
        try:
            with open(os.path.join(module_root, "module.json"), encoding="utf-8") as f:
                module_meta = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            return jsonify({"error": f"module.json illisible : {e}"}), 400

        module_id = module_meta.get("id", "").strip()
        if not module_id or not ALLOWED_ID_PATTERN.match(module_id):
            return jsonify({"error": "id de module manquant ou invalide dans module.json "
                                      "(lettres minuscules, chiffres, '-', '_' uniquement)"}), 400

        if not os.path.exists(os.path.join(module_root, "entry.py")):
            return jsonify({"error": "entry.py introuvable dans l'archive"}), 400

        os.makedirs(MODULES_DIR, exist_ok=True)
        dest_dir = os.path.join(MODULES_DIR, module_id)
        already_existed = os.path.isdir(dest_dir)

        if already_existed:
            shutil.rmtree(dest_dir)
        shutil.copytree(module_root, dest_dir)

    try:
        reload_modules_registery()
    except Exception as e:
        return jsonify({"error": f"Module copié mais échec du rechargement : {e}"}), 500

    action = "mis à jour" if already_existed else "installé"
    return jsonify({
        "ok": True,
        "id": module_id,
        "name": module_meta.get("name", module_id),
        "action": action,
    }), 201


@modules_bp.route("/<module_id>", methods=["DELETE"])
@login_required
@require_modules_write
def delete_module(module_id: str):
    if not ALLOWED_ID_PATTERN.match(module_id):
        return jsonify({"error": "id de module invalide"}), 400

    dest_dir = os.path.join(MODULES_DIR, module_id)
    if not os.path.isdir(dest_dir):
        return jsonify({"error": f"Module '{module_id}' introuvable"}), 404

    shutil.rmtree(dest_dir)
    reload_modules_registery()
    return jsonify({"ok": True, "deleted_id": module_id})


@modules_bp.route("/<module_id>/check-update")
@login_required
def check_update(module_id: str):
    """
    GET /modules/<id>/check-update
    Si le module définit "repository" dans son module.json (URL vers un
    module.json de référence, ex: GitHub raw), compare la version distante
    à la version locale. Champ purement informatif — son absence ne bloque
    rien, l'installation/mise à jour reste manuelle via /modules/install.
    """
    mod = next((m for m in MODULES_REGISTERY if m.id == module_id), None)
    if mod is None:
        return jsonify({"error": f"Module '{module_id}' introuvable"}), 404

    if not mod.repository:
        return jsonify({"checked": False, "reason": "Aucun repository défini pour ce module"})

    try:
        resp = requests.get(mod.repository, timeout=8)
        resp.raise_for_status()
        remote_meta = resp.json()
    except requests.exceptions.RequestException as e:
        return jsonify({"checked": False, "reason": f"Repository inaccessible : {e}"})
    except ValueError:
        return jsonify({"checked": False, "reason": "Réponse du repository invalide (pas un JSON)"})

    remote_version = str(remote_meta.get("version", "")).strip()
    local_version  = str(mod.version or "").strip()

    if not remote_version:
        return jsonify({"checked": False, "reason": "Le repository ne définit pas de champ 'version'"})

    update_available = bool(local_version) and remote_version != local_version

    return jsonify({
        "checked":           True,
        "local_version":     local_version or None,
        "remote_version":    remote_version,
        "update_available":  update_available,
    })