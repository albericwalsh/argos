# Argos — Système de rapports modulaire

## Architecture

```
data/
├── modules/
│   ├── nmap/
│   │   ├── module.json
│   │   ├── entry.py          ← peut contenir pdf_render()
│   │   └── render.html       ← ✨ nouveau : fragment Jinja2 HTML
│   ├── vuln_lookup/
│   │   ├── module.json
│   │   ├── entry.py
│   │   └── render.html
│   ├── debug_input/
│   │   ├── module.json
│   │   ├── entry.py
│   │   └── render.html       ← utiliser debug_render.html
│   └── debug_output/
│       ├── module.json
│       ├── entry.py
│       └── render.html
│
src/
└── core/
    ├── report_engine.py      ← ✨ nouveau moteur modulaire
    └── renders/
        └── generic_render.html  ← fallback pour modules sans render.html
```

## Déploiement

### 1. Copier les fichiers

```bash
# Moteur principal
cp report_engine.py src/core/report_engine.py

# Renderer générique (fallback)
mkdir -p src/core/renders
cp generic_render.html src/core/renders/generic_render.html

# Renderers par module
cp nmap_render.html      data/modules/nmap/render.html
cp vuln_lookup_render.html data/modules/vuln_lookup/render.html
cp debug_render.html     data/modules/debug_input/render.html
cp debug_render.html     data/modules/debug_output/render.html

# Hook PDF optionnel pour nmap (ajouter à la fin de entry.py)
cat nmap_pdf_render.py >> data/modules/nmap/entry.py
```

### 2. Aucune modification requise

- `reports.py` (routes Flask) : **inchangé**
- `reports.html` (template WebUI) : **inchangé**
- `server.py` : **inchangé**

Le nouveau `report_engine.py` est un drop-in replacement de l'ancien.

---

## Créer un renderer pour un nouveau module

Créez `data/modules/<module_id>/render.html` :

```jinja2
{# Variables disponibles : step, step_id, step_index, module #}
{% set output = step.get("output", []) %}

<div class="mod-section">
  <div class="mod-header">
    <div class="mod-header-left">
      <span class="mod-icon">⬡</span>
      <div>
        <div class="mod-name">{{ module.name }}</div>
        <div class="mod-meta">{{ module.category }} · {{ step_id }}</div>
      </div>
    </div>
  </div>

  <!-- Votre rendu custom ici -->
  <div class="table-wrap">
    <table class="mod-table">
      <!-- ... -->
    </table>
  </div>
</div>
```

Les classes CSS partagées (`mod-section`, `mod-header`, `table-wrap`, etc.)
sont injectées par le shell HTML du moteur — inutile de les redéfinir.

### Hook PDF optionnel

Ajoutez une fonction `pdf_render` dans `entry.py` du module :

```python
def pdf_render(step: dict, module: dict, styles: dict, page_width: float):
    """Retourne une liste de Flowables ReportLab."""
    from reportlab.platypus import Paragraph
    output = step.get("output", [])
    # ... construire les flowables
    return [Paragraph("...", styles["body"])]
```

Si absente, le moteur affiche un dump JSON générique dans le PDF.
