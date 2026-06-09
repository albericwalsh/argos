"""
resources.py — WebUI blueprint
Gestion des ressources (wordlists, fichiers de config, etc.)
stockées dans data/ressources/

Routes :
  GET  /resources              → page de gestion
  GET  /resources/list         → JSON liste des fichiers
  POST /resources/upload       → upload d'un fichier
  DELETE /resources/<filename> → suppression
"""

import os
import json
from flask import Blueprint, render_template, request, jsonify, abort
from src.variables import APP_DIR

bp = Blueprint("resources", __name__)

RESOURCES_DIR = os.path.join(APP_DIR, "data", "ressources")

# Extensions autorisées
ALLOWED_EXTENSIONS = {".txt", ".json", ".csv", ".xml", ".lst", ".wordlist", ".conf", ".yaml", ".yml"}
MAX_SIZE_MB = 50


def _ensure_dir():
    os.makedirs(RESOURCES_DIR, exist_ok=True)


def _list_resources() -> list[dict]:
    _ensure_dir()
    files = []
    for fname in sorted(os.listdir(RESOURCES_DIR)):
        fpath = os.path.join(RESOURCES_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        stat = os.stat(fpath)
        size = stat.st_size
        files.append({
            "name":     fname,
            "path":     fpath,
            "size":     size,
            "size_str": _fmt_size(size),
            "ext":      os.path.splitext(fname)[1].lower(),
        })
    return files


def _fmt_size(n: int) -> str:
    if n < 1024:       return f"{n} B"
    if n < 1024**2:    return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


@bp.route("/resources")
def resources_page():
    return render_template("resources.html", resources=_list_resources())


@bp.route("/resources/list")
def resources_list():
    return jsonify(_list_resources())


@bp.route("/resources/upload", methods=["POST"])
def resources_upload():
    _ensure_dir()

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Aucun fichier reçu"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"ok": False, "error": "Nom de fichier vide"}), 400

    # Sécurisation du nom
    filename = os.path.basename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"ok": False, "error": f"Extension '{ext}' non autorisée"}), 400

    dest = os.path.join(RESOURCES_DIR, filename)

    # Lecture avec limite de taille
    data = file.read(MAX_SIZE_MB * 1024 * 1024 + 1)
    if len(data) > MAX_SIZE_MB * 1024 * 1024:
        return jsonify({"ok": False, "error": f"Fichier trop volumineux (max {MAX_SIZE_MB} MB)"}), 400

    with open(dest, "wb") as f:
        f.write(data)

    return jsonify({"ok": True, "name": filename, "path": dest, "size_str": _fmt_size(len(data))})


@bp.route("/resources/<filename>", methods=["DELETE"])
def resources_delete(filename):
    safe = os.path.basename(filename)
    fpath = os.path.join(RESOURCES_DIR, safe)
    if not os.path.exists(fpath):
        return jsonify({"ok": False, "error": "Fichier introuvable"}), 404
    os.remove(fpath)
    return jsonify({"ok": True})