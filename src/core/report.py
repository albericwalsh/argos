"""
report.py
Argos — Report Engine v3 (chiffré)
Génère des rapports HTML/PDF en assemblant les render.html de chaque
module impliqué dans une mission.

SÉCURITÉ — différences avec v2 :
  - generate_report() ne reçoit plus seulement `mission` (dict) mais
    aussi `api_base`, `token`, `owner_key`, `owner_id` : nécessaires pour
    (a) déchiffrer le workflow associé à la mission via l'API plutôt que
        de le lire en clair sur disque (_build_step_module_map)
    (b) chiffrer le rapport HTML/PDF généré avec la clé du owner avant
        de l'envoyer à l'API, plutôt que de l'écrire en clair dans
        REPORTS_DIR
  - list_reports() ne scanne plus un dossier disque local : il interroge
    l'API (GET /files/reports), qui ne retourne que les rapports dont le
    user courant est owner ou pour lesquels il a la permission '*'.
  - Les fichiers PDF (binaires) sont chiffrés en base64 avant l'enveloppe
    AES-GCM (le contenu chiffré transite en JSON, donc en texte).

Cette fonction est appelée depuis une route Flask authentifiée
(src/WebUI/reports.py) qui dispose de g.token et g.enc_key pour le user
courant — ces valeurs ne sont jamais persistées au-delà de la requête.
"""

import base64
import os
import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG      = colors.HexColor("#0d0d0f")
C_SURFACE = colors.HexColor("#141416")
C_BORDER  = colors.HexColor("#2a2a2e")
C_ACCENT  = colors.HexColor("#00e5a0")
C_TEXT    = colors.HexColor("#e8e8ec")
C_MUTED   = colors.HexColor("#6b6b78")
C_HIGH    = colors.HexColor("#ff4d4d")
C_MED     = colors.HexColor("#f5a623")
C_LOW     = colors.HexColor("#4dc8ff")

SEVERITY_COLORS = {
    "CRITICAL": colors.HexColor("#ff2020"),
    "HIGH":     C_HIGH,
    "MEDIUM":   C_MED,
    "LOW":      C_LOW,
    "INFO":     colors.HexColor("#9b9bff"),
}


# ══════════════════════════════════════════════════════════════════════════════
# MODULE REGISTRY HELPERS (inchangé — les modules eux-mêmes ne sont pas
# considérés comme des données sensibles à chiffrer : ce sont du code/
# des définitions d'application, pas des résultats de mission)
# ══════════════════════════════════════════════════════════════════════════════

def _load_module_json(modules_dir: str, module_id: str) -> dict | None:
    path = os.path.join(modules_dir, module_id, "module.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _find_render_template(modules_dir: str, module_id: str) -> str | None:
    path = os.path.join(modules_dir, module_id, "render.html")
    return path if os.path.exists(path) else None


# ══════════════════════════════════════════════════════════════════════════════
# JINJA2 FRAGMENT RENDERER (inchangé)
# ══════════════════════════════════════════════════════════════════════════════

_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_GENERIC_RENDER = os.path.join(_ENGINE_DIR, "renders", "generic_render.html")


def _render_step_fragment(template_path, step, step_id, step_index, module):
    template_dir  = os.path.dirname(os.path.abspath(template_path))
    template_file = os.path.basename(template_path)

    env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)

    def _tojson(v, indent=None):
        def _default(obj):
            try:
                import dataclasses
                if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                    return dataclasses.asdict(obj)
            except Exception:
                pass
            if hasattr(obj, "_asdict"):
                return obj._asdict()  # type: ignore
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)
        return json.dumps(v, ensure_ascii=False, indent=indent, default=_default)

    env.filters["tojson"] = _tojson
    env.filters["fromjson"] = json.loads

    def _index_by(items, key):
        """
        Filtre Jinja : transforme une liste de dicts en dict indexé par
        une clé donnée. Utilisé par les modules (ex: paramspider) pour
        retrouver rapidement le détail d'une URL sans recourir à un
        pattern dict.update() en boucle, plus fragile et illisible
        dans un template.
        Usage : {% set by_url = results | index_by("url") %}
        """
        out = {}
        for item in items or []:
            if isinstance(item, dict) and key in item:
                out[item[key]] = item
        return out

    env.filters["index_by"] = _index_by

    tmpl = env.get_template(template_file)
    return tmpl.render(step=step, step_id=step_id, step_index=step_index, module=module or {})


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UTILITAIRES (inchangé)
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso or "—"


def _duration(start: str, end: str) -> str:
    try:
        d = datetime.fromisoformat(end) - datetime.fromisoformat(start)
        secs = int(d.total_seconds())
        return f"{secs // 60}m {secs % 60}s"
    except Exception:
        return "—"


# ══════════════════════════════════════════════════════════════════════════════
# HTML GENERATION — DYNAMIC (logique de rendu inchangée, seule la source
# du mapping step→module change : déchiffrée via API au lieu du disque)
# ══════════════════════════════════════════════════════════════════════════════

_HTML_SHELL = """\
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Argos — {mission_id}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
  :root {{
    --bg: #0d0d0f; --surface: #141416; --surface2: #1c1c20;
    --border: #2a2a2e; --border-hover: #3a3a3e;
    --accent: #00e5a0; --text: #e8e8ec; --muted: #6b6b78;
    --font-mono: 'IBM Plex Mono', monospace;
    --font-sans: 'IBM Plex Sans', sans-serif;
  }}
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text); font-family: var(--font-sans);
    font-size: 13px; line-height: 1.6; padding: 40px;
  }}
  .report-header {{
    border-bottom: 1px solid var(--border);
    padding-bottom: 24px; margin-bottom: 36px;
    display: flex; justify-content: space-between; align-items: flex-start;
  }}
  .report-brand {{
    font-family: var(--font-mono); font-size: 11px; color: var(--accent);
    letter-spacing: .12em; text-transform: uppercase; margin-bottom: 8px;
  }}
  .report-title {{ font-size: 22px; font-weight: 600; margin-bottom: 4px; }}
  .report-sub {{ color: var(--muted); font-family: var(--font-mono); font-size: 11px; }}
  .report-meta {{
    text-align: right; font-family: var(--font-mono); font-size: 11px;
    color: var(--muted); line-height: 1.9;
  }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 3px;
    font-family: var(--font-mono); font-size: 10px; font-weight: 600;
    letter-spacing: .06em; text-transform: uppercase;
  }}
  .badge-completed {{ background: rgba(0,229,160,.12); color: var(--accent); border: 1px solid rgba(0,229,160,.3); }}
  .badge-failed    {{ background: rgba(255,77,77,.12);  color: #ff4d4d;       border: 1px solid rgba(255,77,77,.3); }}
  .badge-running   {{ background: rgba(245,166,35,.12); color: #f5a623;       border: 1px solid rgba(245,166,35,.3); }}
  .section {{ margin-bottom: 36px; }}
  .section-title {{
    font-family: var(--font-mono); font-size: 10px; letter-spacing: .14em;
    text-transform: uppercase; color: var(--accent);
    padding-bottom: 8px; border-bottom: 1px solid var(--border); margin-bottom: 16px;
  }}
  .meta-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 1px; background: var(--border); border: 1px solid var(--border);
    border-radius: 4px; overflow: hidden;
  }}
  .meta-cell {{ background: var(--surface); padding: 12px 16px; }}
  .meta-label {{
    font-family: var(--font-mono); font-size: 10px; color: var(--muted);
    text-transform: uppercase; letter-spacing: .08em; margin-bottom: 4px;
  }}
  .meta-value {{ font-family: var(--font-mono); font-size: 12px; color: var(--text); font-weight: 600; }}
  .pipeline {{
    display: flex; align-items: center; gap: 0;
    margin-bottom: 28px; overflow-x: auto;
  }}
  .pipeline-step {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 16px;
    background: var(--surface); border: 1px solid var(--border);
    font-family: var(--font-mono); font-size: 10px; color: var(--muted);
    white-space: nowrap;
  }}
  .pipeline-step:first-child {{ border-radius: 4px 0 0 4px; }}
  .pipeline-step:last-child  {{ border-radius: 0 4px 4px 0; }}
  .pipeline-step + .pipeline-step {{ border-left: none; }}
  .pipeline-step-id {{ color: var(--accent); font-weight: 600; }}
  .pipeline-arrow {{ color: var(--muted); font-size: 12px; }}
  .mod-section {{ margin-bottom: 32px; }}
  .mod-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 18px;
    background: var(--surface); border: 1px solid var(--border);
    border-bottom: none; border-radius: 4px 4px 0 0;
  }}
  .mod-header-left {{ display: flex; align-items: center; gap: 12px; }}
  .mod-icon {{ font-size: 20px; color: var(--accent); line-height: 1; opacity: .7; }}
  .mod-name  {{ font-size: 13px; font-weight: 600; }}
  .mod-meta  {{ font-family: var(--font-mono); font-size: 10px; color: var(--muted); margin-top: 1px; }}
  .mod-stats {{ display: flex; gap: 24px; }}
  .mod-stat  {{ text-align: right; }}
  .mod-stat-num {{ font-family: var(--font-mono); font-size: 18px; font-weight: 700; display: block; line-height: 1; }}
  .mod-stat-lbl {{ font-family: var(--font-mono); font-size: 9px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }}
  .table-wrap {{ border: 1px solid var(--border); border-radius: 0 0 4px 4px; overflow: hidden; }}
  .mod-empty {{
    padding: 32px; text-align: center; color: var(--muted);
    font-family: var(--font-mono); font-size: 11px;
    border: 1px solid var(--border); border-top: none;
    border-radius: 0 0 4px 4px;
  }}
  .report-footer {{
    margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border);
    display: flex; justify-content: space-between;
    font-family: var(--font-mono); font-size: 10px; color: var(--muted);
  }}
</style>
</head>
<body>

<div class="report-header">
  <div>
    <div class="report-brand">▸ Argos Security Platform — Scan Report</div>
    <div class="report-title">{mission_name}</div>
    <div class="report-sub">{mission_id} &nbsp;·&nbsp; Workflow: {workflow}</div>
  </div>
  <div class="report-meta">
    <span class="badge badge-{status_lower}">{status}</span><br><br>
    Généré le {generated_at}<br>
    Cible: <strong style="color:var(--text)">{target}</strong><br>
    Durée: {duration}
  </div>
</div>

<div class="section">
  <div class="section-title">// Paramètres de la mission</div>
  <div class="meta-grid">{meta_cells}</div>
</div>

<div class="section">
  <div class="section-title">// Pipeline d'exécution</div>
  <div class="pipeline">{pipeline_steps}</div>
</div>

{step_fragments}

<div class="report-footer">
  <span>Argos Security Platform</span>
  <span>Rapport confidentiel — usage interne</span>
  <span>Généré le {generated_at}</span>
</div>

</body>
</html>
"""


def _build_step_module_map(mission: dict, api_base: str, token: str) -> dict[str, str]:
    """
    Construit {step_id: module_id} en déchiffrant le workflow associé
    via l'API (jamais de lecture disque en clair).

    Le user courant (token) doit être owner du workflow OU disposer de
    workflows:* pour que l'API accepte de résoudre la clé de déchiffrement
    — sinon l'appel échoue et on retombe sur le renderer générique.
    """
    workflow_id = mission.get("workflow", "")
    if not workflow_id:
        return {}

    try:
        from src.WebUI.crypto_bridge import fetch_and_decrypt_json
        wf = fetch_and_decrypt_json(api_base, token, f"/files/workflows/{workflow_id}.json")
        return {s["id"]: s["module"] for s in wf.get("steps", []) if "id" in s and "module" in s}
    except Exception as e:
        print(f"[report] Impossible de déchiffrer le workflow {workflow_id} : {e}")
        return {}


def generate_html(mission: dict, modules_dir: str, api_base: str, token: str) -> str:
    inputs = mission.get("inputs") or {}
    result = mission.get("result", {}) or {}
    if not inputs:
        inputs = result.get("inputs") or {}

    meta_cells = ""
    for k, v in inputs.items():
        meta_cells += (
            f'<div class="meta-cell">'
            f'<div class="meta-label">{k}</div>'
            f'<div class="meta-value">{v or "—"}</div>'
            f'</div>'
        )

    step_keys = [k for k in result if k != "inputs"]

    pipeline_steps = ""
    for i, sid in enumerate(step_keys):
        if i > 0:
            pipeline_steps += '<span class="pipeline-arrow">→</span>'
        pipeline_steps += f'<div class="pipeline-step"><span class="pipeline-step-id">{sid}</span></div>'

    step_module_map = _build_step_module_map(mission, api_base, token)

    step_fragments = ""
    for idx, step_id in enumerate(step_keys):
        step_data   = result[step_id]
        module_id   = step_module_map.get(step_id)
        module_meta = _load_module_json(modules_dir, module_id) if module_id else None
        render_path = _find_render_template(modules_dir, module_id) if module_id else None

        if render_path is None:
            render_path = _GENERIC_RENDER

        module_label = (module_meta.get("name") if module_meta else module_id) or step_id
        step_fragments += (
            f'<div class="section">'
            f'<div class="section-title">// Step {idx + 1} — {step_id}'
            f'{" · " + module_label if module_label != step_id else ""}'
            f'</div>'
        )
        step_fragments += _render_step_fragment(render_path, step_data, step_id, idx, module_meta)
        step_fragments += '</div>'

    return _HTML_SHELL.format(
        mission_id     = mission.get("id", "—"),
        mission_name   = mission.get("name", "Rapport de mission"),
        workflow       = mission.get("workflow", "—"),
        status         = mission.get("status", "—").upper(),
        status_lower   = mission.get("status", "pending").lower(),
        target         = inputs.get("target") or inputs.get("domaine") or next(iter(inputs.values()), "—"),
        duration       = _duration(mission.get("date_created", ""), mission.get("date_completed", "")),
        generated_at   = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        meta_cells     = meta_cells,
        pipeline_steps = pipeline_steps,
        step_fragments = step_fragments,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATION (logique de rendu inchangée)
# ══════════════════════════════════════════════════════════════════════════════

def _styles():
    def S(name, **kw):
        return ParagraphStyle(name, **kw)
    return {
        "brand":    S("brand",    fontName="Helvetica",      fontSize=8,  textColor=C_ACCENT, spaceAfter=2),
        "title":    S("title",    fontName="Helvetica-Bold", fontSize=18, textColor=C_TEXT,   spaceAfter=4),
        "sub":      S("sub",      fontName="Helvetica",      fontSize=9,  textColor=C_MUTED,  spaceAfter=0),
        "section":  S("section",  fontName="Helvetica-Bold", fontSize=8,  textColor=C_ACCENT, spaceBefore=18, spaceAfter=6),
        "body":     S("body",     fontName="Helvetica",      fontSize=9,  textColor=C_TEXT),
        "mono":     S("mono",     fontName="Courier",        fontSize=8,  textColor=C_TEXT),
        "mono_mut": S("mono_mut", fontName="Courier",        fontSize=8,  textColor=C_MUTED),
        "small":    S("small",    fontName="Helvetica",      fontSize=8,  textColor=C_MUTED),
    }


def _tbl_style():
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_MUTED),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR",     (0, 1), (-1, -1), C_TEXT),
        ("BACKGROUND",    (0, 1), (-1, -1), C_BG),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_BG, colors.HexColor("#161618")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])


def generate_pdf_bytes(mission: dict, modules_dir: str, api_base: str, token: str) -> bytes:
    """
    Génère le PDF en mémoire (BytesIO) au lieu d'écrire directement sur
    disque en clair — le PDF est ensuite chiffré par l'appelant avant
    d'être envoyé à l'API.
    """
    import io
    inputs = mission.get("inputs") or {}
    result = mission.get("result", {}) or {}
    if not inputs:
        inputs = result.get("inputs") or {}
    step_keys = [k for k in result if k != "inputs"]

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=16*mm,
        title=f"Argos Report — {mission.get('id', '')}",
    )
    W  = A4[0] - 36*mm
    st = _styles()
    story = []

    story.append(Paragraph("▸ ARGOS SECURITY PLATFORM — SCAN REPORT", st["brand"]))
    story.append(Paragraph(mission.get("name", "Rapport de mission"), st["title"]))
    story.append(Paragraph(
        f"{mission.get('id','—')}  ·  Workflow: {mission.get('workflow','—')}  ·  "
        f"Cible: {inputs.get('target','—')}  ·  "
        f"Durée: {_duration(mission.get('date_created',''), mission.get('date_completed',''))}",
        st["sub"]
    ))
    story.append(HRFlowable(width=W, thickness=0.5, color=C_BORDER, spaceAfter=12))

    story.append(Paragraph("// PARAMÈTRES DE LA MISSION", st["section"]))
    in_data = [["Paramètre", "Valeur"]]
    for k, v in inputs.items():
        in_data.append([Paragraph(k, st["mono_mut"]), Paragraph(str(v) if v else "—", st["mono"])])  # type: ignore
    story.append(Table(in_data, colWidths=[60*mm, W - 60*mm], style=_tbl_style()))

    step_module_map = _build_step_module_map(mission, api_base, token)

    for idx, step_id in enumerate(step_keys):
        step_data    = result[step_id]
        module_id    = step_module_map.get(step_id)
        module_meta  = _load_module_json(modules_dir, module_id) if module_id else None
        module_label = (module_meta.get("name") if module_meta else module_id) or step_id

        story.append(Paragraph(f"// {step_id.upper()} — {module_label.upper()}", st["section"]))

        pdf_flowables = _try_module_pdf_render(modules_dir, module_id, step_data, module_meta, st, W)
        if pdf_flowables:
            story.extend(pdf_flowables)
        else:
            output = step_data.get("output")
            error  = step_data.get("error")
            if error:
                story.append(Paragraph(f"Erreur: {str(error)[:200]}", st["small"]))
            elif output is not None:
                text = json.dumps(output, ensure_ascii=False, indent=2,
                                   default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o))[:800]
                story.append(Paragraph(text.replace("\n", "<br/>"), st["mono_mut"]))
            else:
                story.append(Paragraph("Pas de sortie.", st["small"]))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width=W, thickness=0.4, color=C_BORDER))
    story.append(Paragraph(
        f"Argos Security Platform  ·  Rapport confidentiel – usage interne  ·  "
        f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        st["small"]
    ))

    doc.build(story)
    return buf.getvalue()


def _try_module_pdf_render(modules_dir, module_id, step_data, module_meta, st, W):
    if not module_id:
        return None
    entry_path = os.path.join(modules_dir, module_id, "entry.py")
    if not os.path.exists(entry_path):
        return None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(f"argos_module_{module_id}", entry_path)
        if spec is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        if not hasattr(mod, "pdf_render"):
            return None
        return mod.pdf_render(step_data, module_meta, st, W)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — chiffrement à l'écriture, plus d'écriture disque en clair
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(mission: dict, api_base: str, token: str, owner_key: str) -> dict:
    """
    Génère HTML + PDF pour une mission, CHIFFRE chaque fichier avec la
    clé du user qui demande le rapport (owner_key, reçue depuis g.enc_key
    de la requête authentifiée), puis les envoie à l'API via PUT.

    Aucun fichier en clair n'est écrit sur disque à aucun moment.

    Retourne {"id": mission_id, "html_filename": ..., "pdf_filename": ...}.
    """
    from src.variables import APP_DIR
    from src.WebUI.crypto_bridge import encrypt_and_put_json_with_key
    from src.crypto_utils import encrypt_bytes

    modules_dir = os.path.join(APP_DIR, "data", "modules")  # définitions de modules : non sensible, reste sur disque
    mission_id   = mission.get("id", "unknown").lstrip("#").replace(" ", "_")
    mission_name = mission.get("name", "") or mission_id

    html_content = generate_html(mission, modules_dir, api_base, token)
    pdf_bytes    = generate_pdf_bytes(mission, modules_dir, api_base, token)

    # ── HTML : chiffré comme un JSON wrapper { "html": "<...>" } pour
    #    réutiliser le même format d'enveloppe que les autres fichiers ──
    html_filename = f"{mission_id}.html"
    envelope_html = encrypt_bytes(html_content.encode("utf-8"), owner_key)
    envelope_html["original_name"] = html_filename
    envelope_html["mission_name"]  = mission_name
    _put_report_envelope(api_base, token, html_filename, envelope_html)

    # ── PDF : binaire, encodé en base64 avant chiffrement (le contenu
    #    chiffré est transporté en JSON donc doit être texte) ──
    pdf_filename = f"{mission_id}.pdf"
    pdf_b64      = base64.b64encode(pdf_bytes).decode("ascii")
    envelope_pdf = encrypt_bytes(pdf_b64.encode("utf-8"), owner_key)
    envelope_pdf["original_name"] = pdf_filename
    envelope_pdf["mission_name"]  = mission_name
    _put_report_envelope(api_base, token, pdf_filename, envelope_pdf)

    return {"id": mission_id, "html_filename": html_filename, "pdf_filename": pdf_filename}


def _put_report_envelope(api_base: str, token: str, filename: str, envelope: dict):
    import requests
    resp = requests.put(
        f"{api_base}/files/reports/{filename}",
        headers={"Authorization": f"Bearer {token}"},
        json=envelope,
        timeout=15,
    )
    resp.raise_for_status()


def list_reports(api_base: str, token: str) -> list[dict]:
    """
    Liste les rapports visibles par le user courant via l'API
    (owner ou permission rapports:*). Remplace l'ancien scan disque.

    Retourne une liste de dicts {id, html_file, pdf_file, generated,
    mission_name} compatible avec le template reports.html.
    """
    import requests

    try:
        resp = requests.get(
            f"{api_base}/files/reports",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        resp.raise_for_status()
        files = resp.json()
    except Exception as e:
        print(f"[report] Impossible de lister les rapports : {e}")
        return []

    seen: dict[str, dict] = {}
    for f in files:
        original = f.get("original_name", "")
        base, ext = os.path.splitext(original)
        if ext not in (".html", ".pdf"):
            continue
        if base not in seen:
            seen[base] = {
                "id":           base,
                "html_file":    None,
                "pdf_file":     None,
                "mtime":        0,
                "mission_name": f.get("mission_name") or base,
            }
        seen[base][f"{ext[1:]}_file"] = f["name"]
        # Garde le mtime le plus récent entre html et pdf pour ce rapport
        seen[base]["mtime"] = max(seen[base]["mtime"], f.get("mtime", 0))
        if f.get("mission_name") and not seen[base].get("mission_name_set"):
            seen[base]["mission_name"] = f["mission_name"]
            seen[base]["mission_name_set"] = True

    result = []
    for base, info in sorted(seen.items(), key=lambda kv: kv[1]["mtime"], reverse=True):
        generated = (
            datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M")
            if info["mtime"] else "—"
        )
        result.append({
            "id":           base,
            "html_file":    info["html_file"],
            "pdf_file":     info["pdf_file"],
            "generated":    generated,
            "mission_name": info["mission_name"],
        })
    return result


def fetch_report_html(api_base: str, token: str, enc_key: str, filename: str) -> str:
    """Récupère et déchiffre un rapport HTML pour aperçu côté serveur si besoin."""
    from src.WebUI.crypto_bridge import fetch_and_decrypt_json
    # Le rapport HTML est stocké comme texte chiffré directement (pas un dict JSON) ;
    # on réutilise decrypt_bytes directement plutôt que fetch_and_decrypt_json
    # qui s'attend à du JSON. Voir reports.py pour l'implémentation d'aperçu.
    raise NotImplementedError("Utiliser la route /reports/preview de reports.py")