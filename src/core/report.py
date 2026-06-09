"""
report_engine.py
Argos — Report Engine v2
Génère des rapports HTML dynamiques en assemblant les render.html
de chaque module impliqué dans une mission.

Architecture :
  - Chaque module peut fournir un fichier render.html dans son dossier.
  - Le moteur charge ces fragments via Jinja2 et les injecte dans le
    layout principal du rapport.
  - Si un module n'a pas de render.html, un renderer générique (JSON dump)
    est utilisé automatiquement.
  - La génération PDF reste assurée par ReportLab (rendu statique à partir
    du HTML généré).
"""

import os
import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, BaseLoader, TemplateNotFound

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
# MODULE REGISTRY HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _load_module_json(modules_dir: str, module_id: str) -> dict | None:
    """Charge le module.json d'un module donné."""
    path = os.path.join(modules_dir, module_id, "module.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _find_render_template(modules_dir: str, module_id: str) -> str | None:
    """
    Retourne le chemin absolu vers render.html du module, ou None si absent.
    """
    path = os.path.join(modules_dir, module_id, "render.html")
    return path if os.path.exists(path) else None


def _resolve_step_module(mission: dict, step_id: str, workflow_steps: list) -> str | None:
    """
    Retrouve le module_id associé à un step_id en parcourant
    la définition de workflow stockée dans la mission.
    """
    for step in workflow_steps:
        if step.get("id") == step_id:
            return step.get("module")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# JINJA2 FRAGMENT RENDERER
# ══════════════════════════════════════════════════════════════════════════════

# Chemin vers le render.html générique (dans le même dossier que ce fichier)
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_GENERIC_RENDER = os.path.join(_ENGINE_DIR, "renders", "generic_render.html")


def _render_step_fragment(
    template_path: str,
    step: dict,
    step_id: str,
    step_index: int,
    module: dict | None,
) -> str:
    """
    Rend un fragment HTML pour un step donné en utilisant le template Jinja2
    fourni (render.html du module, ou generic_render.html).
    """
    template_dir  = os.path.dirname(os.path.abspath(template_path))
    template_file = os.path.basename(template_path)

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=False,  # HTML brut, les données sont de confiance (interne)
    )
    def _tojson(v, indent=None):
        def _default(obj):
            try:
                import dataclasses
                if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
                    return dataclasses.asdict(obj)
            except Exception:
                pass
            if hasattr(obj, "_asdict"):
                return obj._asdict() # type: ignore
            if hasattr(obj, "__dict__"):
                return obj.__dict__
            return str(obj)
        return json.dumps(v, ensure_ascii=False, indent=indent, default=_default)

    env.filters["tojson"] = _tojson
    env.filters["fromjson"] = json.loads
    
    tmpl = env.get_template(template_file)
    return tmpl.render(
        step=step,
        step_id=step_id,
        step_index=step_index,
        module=module or {},
    )


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS UTILITAIRES
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
# HTML GENERATION — DYNAMIC
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

  /* ── Report header ── */
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

  /* ── Inputs section ── */
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

  /* ── Step pipeline ── */
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

  /* ── Shared module section styles (each render.html extends these) ── */
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

  /* ── Footer ── */
  .report-footer {{
    margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--border);
    display: flex; justify-content: space-between;
    font-family: var(--font-mono); font-size: 10px; color: var(--muted);
  }}
</style>
</head>
<body>

<!-- ── Header ── -->
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

<!-- ── Inputs ── -->
<div class="section">
  <div class="section-title">// Paramètres de la mission</div>
  <div class="meta-grid">{meta_cells}</div>
</div>

<!-- ── Pipeline ── -->
<div class="section">
  <div class="section-title">// Pipeline d'exécution</div>
  <div class="pipeline">{pipeline_steps}</div>
</div>

<!-- ── Step fragments ── -->
{step_fragments}

<!-- ── Footer ── -->
<div class="report-footer">
  <span>Argos Security Platform</span>
  <span>Rapport confidentiel — usage interne</span>
  <span>Généré le {generated_at}</span>
</div>

</body>
</html>
"""


def generate_html(mission: dict, modules_dir: str) -> str:
    inputs  = mission.get("inputs") or {}
    result  = mission.get("result", {}) or {}
    # Fallback : workflow.run() stocke toujours les inputs dans result["inputs"]
    if not inputs:
        inputs = result.get("inputs") or {}

    # ── Meta cells ──────────────────────────────────────────────────────────
    meta_cells = ""
    for k, v in inputs.items():
        meta_cells += (
            f'<div class="meta-cell">'
            f'<div class="meta-label">{k}</div>'
            f'<div class="meta-value">{v or "—"}</div>'
            f'</div>'
        )

    # ── Identify steps in result (skip "inputs" key) ───────────────────────
    step_keys = [k for k in result if k != "inputs"]

    # ── Pipeline visualisation ──────────────────────────────────────────────
    pipeline_steps = ""
    for i, sid in enumerate(step_keys):
        if i > 0:
            pipeline_steps += '<span class="pipeline-arrow">→</span>'
        pipeline_steps += (
            f'<div class="pipeline-step">'
            f'<span class="pipeline-step-id">{sid}</span>'
            f'</div>'
        )

    # ── Step fragments ───────────────────────────────────────────────────────
    # Try to load the workflow JSON to map step_id → module_id
    # The mission stores `workflow` as a string id; we need the actual
    # workflow definition to know which module handles which step.
    # We support two approaches:
    #   1. result contains a "_workflow_steps" hint (future enhancement)
    #   2. We infer module_id by scanning modules_dir for a match by name
    #      (fallback: use generic renderer)

    # Build a step→module_id mapping from workflow files
    step_module_map = _build_step_module_map(mission, modules_dir)

    step_fragments = ""
    for idx, step_id in enumerate(step_keys):
        step_data  = result[step_id]
        module_id  = step_module_map.get(step_id)
        module_meta = _load_module_json(modules_dir, module_id) if module_id else None
        render_path = _find_render_template(modules_dir, module_id) if module_id else None

        if render_path is None:
            # Use generic renderer
            render_path = _GENERIC_RENDER

        # Add a section title before each fragment
        module_label = (module_meta.get("name") if module_meta else module_id) or step_id
        step_fragments += (
            f'<div class="section">'
            f'<div class="section-title">// Step {idx + 1} — {step_id}'
            f'{" · " + module_label if module_label != step_id else ""}'
            f'</div>'
        )
        step_fragments += _render_step_fragment(
            template_path=render_path,
            step=step_data,
            step_id=step_id,
            step_index=idx,
            module=module_meta,
        )
        step_fragments += '</div>'

    return _HTML_SHELL.format(
        mission_id    = mission.get("id", "—"),
        mission_name  = mission.get("name", "Rapport de mission"),
        workflow      = mission.get("workflow", "—"),
        status        = mission.get("status", "—").upper(),
        status_lower  = mission.get("status", "pending").lower(),
        target        = inputs.get("target") or inputs.get("domaine") or next(iter(inputs.values()), "—"),
        duration      = _duration(
                            mission.get("date_created", ""),
                            mission.get("date_completed", "")
                        ),
        generated_at  = datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        meta_cells    = meta_cells,
        pipeline_steps= pipeline_steps,
        step_fragments= step_fragments,
    )


def _build_step_module_map(mission: dict, modules_dir: str) -> dict[str, str]:
    """
    Construit un dict {step_id: module_id} à partir du fichier workflow
    correspondant à la mission.

    Cherche le workflow dans APP_DIR/data/workflows/{workflow_id}.json.
    Si introuvable, retourne un dict vide (le renderer générique sera utilisé).
    """
    from src.variables import APP_DIR
    workflow_id = mission.get("workflow", "")
    if not workflow_id:
        return {}

    wf_path = os.path.join(APP_DIR, "data", "workflows", f"{workflow_id}.json")
    if not os.path.exists(wf_path):
        return {}

    try:
        with open(wf_path, encoding="utf-8") as f:
            wf = json.load(f)
        return {step["id"]: step["module"] for step in wf.get("steps", []) if "id" in step and "module" in step}
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATION (statique, résumé structuré)
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


def generate_pdf(mission: dict, out_path: str, modules_dir: str) -> str:
    inputs  = mission.get("inputs") or {}
    result  = mission.get("result", {}) or {}
    # Fallback : workflow.run() stocke toujours les inputs dans result["inputs"]
    if not inputs:
        inputs = result.get("inputs") or {}
    step_keys = [k for k in result if k != "inputs"]

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=16*mm, bottomMargin=16*mm,
        title=f"Argos Report — {mission.get('id', '')}",
    )
    W  = A4[0] - 36*mm
    st = _styles()
    story = []

    # Header
    story.append(Paragraph("▸ ARGOS SECURITY PLATFORM — SCAN REPORT", st["brand"]))
    story.append(Paragraph(mission.get("name", "Rapport de mission"), st["title"]))
    story.append(Paragraph(
        f"{mission.get('id','—')}  ·  Workflow: {mission.get('workflow','—')}  ·  "
        f"Cible: {inputs.get('target','—')}  ·  "
        f"Durée: {_duration(mission.get('date_created',''), mission.get('date_completed',''))}",
        st["sub"]
    ))
    story.append(HRFlowable(width=W, thickness=0.5, color=C_BORDER, spaceAfter=12))

    # Inputs
    story.append(Paragraph("// PARAMÈTRES DE LA MISSION", st["section"]))
    in_data = [["Paramètre", "Valeur"]]
    for k, v in inputs.items():
        in_data.append([Paragraph(k, st["mono_mut"]), Paragraph(str(v) if v else "—", st["mono"])])  # type: ignore
    story.append(Table(in_data, colWidths=[60*mm, W - 60*mm], style=_tbl_style()))

    # Steps — each module can optionally provide a pdf_render(step, module_meta) → list[Flowable]
    # If not available, a generic JSON dump is rendered.
    step_module_map = _build_step_module_map(mission, modules_dir)

    for idx, step_id in enumerate(step_keys):
        step_data  = result[step_id]
        module_id  = step_module_map.get(step_id)
        module_meta = _load_module_json(modules_dir, module_id) if module_id else None
        module_label = (module_meta.get("name") if module_meta else module_id) or step_id

        story.append(Paragraph(
            f"// {step_id.upper()} — {module_label.upper()}",
            st["section"]
        ))

        # Try to call pdf_render from module's entry.py
        pdf_flowables = _try_module_pdf_render(modules_dir, module_id, step_data, module_meta, st, W)
        if pdf_flowables:
            story.extend(pdf_flowables)
        else:
            # Generic: JSON dump
            output = step_data.get("output")
            error  = step_data.get("error")
            if error:
                story.append(Paragraph(f"Erreur: {str(error)[:200]}", st["small"]))
            elif output is not None:
                text = json.dumps(output, ensure_ascii=False, indent=2, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o))[:800]
                story.append(Paragraph(text.replace("\n", "<br/>"), st["mono_mut"]))
            else:
                story.append(Paragraph("Pas de sortie.", st["small"]))

    # Footer
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width=W, thickness=0.4, color=C_BORDER))
    story.append(Paragraph(
        f"Argos Security Platform  ·  Rapport confidentiel – usage interne  ·  "
        f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        st["small"]
    ))

    doc.build(story)
    return out_path


def _try_module_pdf_render(modules_dir, module_id, step_data, module_meta, st, W):
    """
    Tente de charger la fonction pdf_render(step, module, styles, page_width)
    depuis le entry.py du module. Retourne une liste de Flowables ou None.
    """
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
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def generate_report(mission: dict, reports_dir: str) -> dict:
    """
    Génère HTML + PDF pour une mission.
    Retourne {"html": path, "pdf": path, "id": mission_id}
    """
    from src.variables import APP_DIR
    modules_dir = os.path.join(APP_DIR, "data", "modules")

    mission_id = mission.get("id", "unknown").lstrip("#").replace(" ", "_")
    os.makedirs(reports_dir, exist_ok=True)

    html_path = os.path.join(reports_dir, f"{mission_id}.html")
    pdf_path  = os.path.join(reports_dir, f"{mission_id}.pdf")

    html_content = generate_html(mission, modules_dir)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    generate_pdf(mission, pdf_path, modules_dir)

    return {"html": html_path, "pdf": pdf_path, "id": mission_id}


def list_reports(reports_dir: str) -> list[dict]:
    """
    Scanne le dossier reports_dir et retourne les métadonnées de chaque rapport.
    """
    os.makedirs(reports_dir, exist_ok=True)
    seen: dict[str, dict] = {}
    for fname in os.listdir(reports_dir):
        base, ext = os.path.splitext(fname)
        if ext not in (".html", ".pdf"):
            continue
        if base not in seen:
            seen[base] = {"id": base, "html": None, "pdf": None, "mtime": 0}
        path = os.path.join(reports_dir, fname)
        seen[base][ext[1:]] = fname
        seen[base]["mtime"] = max(seen[base]["mtime"], os.path.getmtime(path))

    reports = []
    for base, info in seen.items():
        reports.append({
            "id":        info["id"],
            "html_file": info.get("html"),
            "pdf_file":  info.get("pdf"),
            "generated": datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return sorted(reports, key=lambda r: r["generated"], reverse=True)