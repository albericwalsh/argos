"""
ParamSpider — module Argos
───────────────────────────
Réimplémentation en Python pur de la logique ParamSpider : interroge la
Wayback Machine (CDX API) pour récupérer les URLs historiquement archivées
d'un domaine, puis extrait les paramètres de requête (?key=value) trouvés.

Aucune dépendance externe (pas de package PyPI paramspider, pas de Docker) —
uniquement des requêtes HTTP vers web.archive.org via `requests`, déjà
présent dans l'environnement du projet.

main(args: dict) -> dict
    {
        "domain": str,
        "urls": [str, ...],          # URLs avec paramètres, dédoublonnées
        "parameters": [str, ...],    # noms de paramètres uniques trouvés
        "count_urls": int,
        "count_parameters": int,
    }
"""

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

CDX_API_URL = "http://web.archive.org/cdx/search/cdx"

DEFAULT_EXCLUDED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "svg", "ico", "webp", "bmp",
    "css", "js", "woff", "woff2", "ttf", "eot",
    "mp4", "mp3", "avi", "mov", "pdf", "zip", "rar",
}

# ── Vérification de statut HTTP ────────────────────────────────────────────────
STATUS_CHECK_TIMEOUT     = 6     # secondes par requête
STATUS_CHECK_MAX_WORKERS = 10    # requêtes concurrentes max
STATUS_CHECK_MAX_URLS    = 300   # plafond d'URLs vérifiées (évite l'explosion sur des milliers de résultats)


@dataclass
class ParamUrl:
    """Une URL archivée contenant au moins un paramètre de requête."""
    url: str
    parameters: list = field(default_factory=list)
    status_code: int | None = None      # code HTTP final (après redirections)
    final_url: str | None = None        # URL finale si redirection suivie
    error: str | None = None            # message d'erreur réseau, si la requête a échoué


# ─── Extraction de la cible depuis différentes formes d'input ────────────────

def _extract_domain(target) -> str:
    """
    Normalise `target` en un nom de domaine unique, quelle que soit sa forme
    d'origine :
      - str simple              → "example.com"
      - str URL complète         → extrait le netloc
      - list                     → prend le premier élément non vide
      - dict (sortie d'un autre module, ex: $nmap.output)
                                  → cherche les clés usuelles (host, target,
                                    domain, ip), ou le premier service nmap
    """
    if target is None:
        return ""

    if isinstance(target, dict):
        for key in ("domain", "target", "host", "hostname", "ip"):
            val = target.get(key)
            if val:
                return _extract_domain(val)
        # Sortie nmap typique : dict avec une clé "services" ou similaire —
        # pas de domaine direct disponible, on abandonne proprement.
        return ""

    if isinstance(target, list):
        for item in target:
            domain = _extract_domain(item)
            if domain:
                return domain
        return ""

    target = str(target).strip()
    if not target:
        return ""

    # Si c'est une URL complète, extrait le netloc (host, sans port/scheme)
    if "://" in target:
        parsed = urlparse(target)
        return parsed.netloc.split(":")[0]

    # Sinon, suppose que c'est déjà un domaine nu ; retire un éventuel chemin
    return target.split("/")[0]


def _parse_extensions(raw) -> set:
    """Parse une chaîne 'png,jpg,css' ou une liste en set d'extensions lowercase."""
    if not raw:
        return set(DEFAULT_EXCLUDED_EXTENSIONS)
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, list):
        items = raw
    else:
        return set(DEFAULT_EXCLUDED_EXTENSIONS)
    return {str(e).strip().lower().lstrip(".") for e in items if str(e).strip()}


# ─── Interrogation Wayback Machine ─────────────────────────────────────────────

def _fetch_archived_urls(domain: str, max_urls: int) -> list:
    """
    Interroge l'API CDX de la Wayback Machine pour récupérer les URLs
    archivées du domaine (et sous-domaines, via le préfixe *.domain).

    Retourne une liste brute d'URLs (str), sans filtrage.
    """
    params = {
        "url": f"*.{domain}/*",
        "output": "text",
        "fl": "original",
        "collapse": "urlkey",
        "limit": str(max_urls),
    }

    try:
        resp = requests.get(CDX_API_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[paramspider] ERROR: échec de la requête vers la Wayback Machine : {e}")
        return []

    lines = resp.text.splitlines()
    return [line.strip() for line in lines if line.strip()]


# ─── Filtrage et extraction des paramètres ────────────────────────────────────

def _has_excluded_extension(url: str, excluded_extensions: set) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(f".{ext}") for ext in excluded_extensions)


def _extract_params_from_urls(urls: list, excluded_extensions: set) -> list:
    """
    Filtre les URLs sans paramètres ou avec extension exclue, puis extrait
    les noms de paramètres de chacune. Retourne une liste de ParamUrl.
    """
    results = []
    seen_urls = set()

    for url in urls:
        if "?" not in url:
            continue
        if _has_excluded_extension(url, excluded_extensions):
            continue
        if url in seen_urls:
            continue

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        if not query_params:
            continue

        seen_urls.add(url)
        results.append(ParamUrl(
            url=url,
            parameters=sorted(query_params.keys()),
        ))

    return results


def _unique_parameter_names(param_urls: list) -> list:
    """Déduit la liste dédoublonnée et triée de tous les noms de paramètres trouvés."""
    names = set()
    for pu in param_urls:
        names.update(pu.parameters)
    return sorted(names)


# ─── Vérification du statut HTTP réel de chaque URL ───────────────────────────

def _check_one_url(pu: ParamUrl) -> None:
    """
    Effectue une requête GET réelle (stream=True, lecture minimale) pour
    obtenir le code de statut HTTP final, sans télécharger tout le corps
    de la réponse — compromis entre fiabilité (GET, pas HEAD, certains
    serveurs traitent les deux différemment) et coût réseau.
    Modifie `pu` en place (status_code, final_url, error).
    """
    try:
        resp = requests.get(
            pu.url,
            timeout=STATUS_CHECK_TIMEOUT,
            stream=True,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (ArgosParamSpider)"},
        )
        pu.status_code = resp.status_code
        if resp.url != pu.url:
            pu.final_url = resp.url
        resp.close()  # ferme la connexion sans lire le corps complet
    except requests.exceptions.RequestException as e:
        pu.error = type(e).__name__


def _verify_status_codes(param_urls: list, max_urls: int = STATUS_CHECK_MAX_URLS) -> int:
    """
    Vérifie le statut HTTP de chaque URL dans param_urls, en concurrence
    limitée. Modifie les objets en place. Si param_urls dépasse max_urls,
    seules les premières max_urls sont vérifiées (les autres restent avec
    status_code=None) — évite de bombarder la cible de milliers de requêtes.
    Retourne le nombre d'URLs effectivement vérifiées.
    """
    to_check = param_urls[:max_urls]
    if not to_check:
        return 0

    with ThreadPoolExecutor(max_workers=STATUS_CHECK_MAX_WORKERS) as executor:
        futures = [executor.submit(_check_one_url, pu) for pu in to_check]
        for future in as_completed(futures):
            future.result()  # propage toute exception inattendue (ne devrait pas arriver, _check_one_url catch déjà)

    return len(to_check)


# ─── Logging (capturé par le tracker SSE via Workflow._run_with_log_capture) ──

def _print_summary(domain: str, param_urls: list, unique_params: list, checked_count: int = 0) -> None:
    print(f"[paramspider] Domaine cible       : {domain}")
    print(f"[paramspider] URLs archivées analysées, {len(param_urls)} avec paramètres retenues")
    print(f"[paramspider] Paramètres uniques  : {len(unique_params)}")
    if unique_params:
        preview = ", ".join(unique_params[:15])
        suffix = "…" if len(unique_params) > 15 else ""
        print(f"[paramspider] Aperçu             : {preview}{suffix}")

    if checked_count:
        status_counts: dict = {}
        errors = 0
        for pu in param_urls[:checked_count]:
            if pu.error:
                errors += 1
            elif pu.status_code is not None:
                status_counts[pu.status_code] = status_counts.get(pu.status_code, 0) + 1

        print(f"[paramspider] Statuts HTTP vérifiés sur {checked_count} URL(s) :")
        for code in sorted(status_counts):
            print(f"[paramspider]   {code} : {status_counts[code]}")
        if errors:
            print(f"[paramspider]   erreurs réseau : {errors}")


# ─── Point d'entrée du module (contrat attendu par Module.execute) ────────────

def main(args: dict) -> dict:
    """
    args:
      target              : str|list|dict — domaine, URL, ou $nmap.output / $other.output
      exclude_extensions  : str           — extensions à exclure, séparées par virgules (optionnel)
      max_urls            : str|int       — limite de résultats CDX (optionnel, défaut 5000)
      verify_status       : bool          — vérifie le code HTTP réel de chaque URL trouvée
                                             (requêtes GET réelles vers la cible — défaut True)
    """
    raw_target          = args.get("target", "")
    raw_exclude         = args.get("exclude_extensions", "")
    raw_max_urls        = args.get("max_urls", 5000)
    raw_verify_status   = args.get("verify_status", True)

    try:
        max_urls = int(raw_max_urls) if raw_max_urls else 5000
    except (TypeError, ValueError):
        max_urls = 5000

    verify_status = raw_verify_status
    if isinstance(verify_status, str):
        verify_status = verify_status.lower() in ("true", "1", "yes")

    domain = _extract_domain(raw_target)
    if not domain:
        print("[paramspider] ERROR: cible invalide ou non résolue en domaine.")
        return {
            "domain": "",
            "urls": [],
            "parameters": [],
            "results": [],
            "count_urls": 0,
            "count_parameters": 0,
            "verified": False,
        }

    excluded_extensions = _parse_extensions(raw_exclude)

    print(f"[paramspider] Interrogation de la Wayback Machine pour *.{domain}/*…")
    raw_urls = _fetch_archived_urls(domain, max_urls)
    print(f"[paramspider] {len(raw_urls)} URL(s) archivée(s) récupérée(s) au total.")

    param_urls = _extract_params_from_urls(raw_urls, excluded_extensions)
    unique_params = _unique_parameter_names(param_urls)

    checked_count = 0
    if verify_status and param_urls:
        n = min(len(param_urls), STATUS_CHECK_MAX_URLS)
        print(f"[paramspider] Vérification du code HTTP réel sur {n} URL(s) "
              f"(GET, {STATUS_CHECK_MAX_WORKERS} en parallèle, timeout {STATUS_CHECK_TIMEOUT}s)…")
        checked_count = _verify_status_codes(param_urls)

    _print_summary(domain, param_urls, unique_params, checked_count)

    return {
        "domain":           domain,
        "urls":             [pu.url for pu in param_urls],
        "parameters":       unique_params,
        # results : détail par URL, incluant le code de statut HTTP réel
        # (None si non vérifié — au-delà de STATUS_CHECK_MAX_URLS ou si
        # verify_status=False), l'URL finale en cas de redirection, et
        # l'erreur réseau éventuelle.
        "results": [
            {
                "url":         pu.url,
                "parameters":  pu.parameters,
                "status_code": pu.status_code,
                "final_url":   pu.final_url,
                "error":       pu.error,
            }
            for pu in param_urls
        ],
        "count_urls":       len(param_urls),
        "count_parameters": len(unique_params),
        "verified":         verify_status,
        "checked_count":    checked_count,
    }


# ─── PDF render hook (appelé automatiquement par report.py si présent) ───────

def pdf_render(step: dict, module: dict, styles: dict, page_width: float):
    """
    Retourne une liste de Flowables ReportLab pour le rendu PDF du module
    ParamSpider. Même contrat que nmap : appelé par
    report._try_module_pdf_render() si la fonction existe dans entry.py.
    """
    from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    output = step.get("output") or {}
    if isinstance(output, str):
        # Sécurité : si jamais output a été sérialisé en string ailleurs
        import json
        try:
            output = json.loads(output)
        except Exception:
            output = {}

    urls       = output.get("urls", []) if isinstance(output, dict) else []
    results    = output.get("results", []) if isinstance(output, dict) else []
    parameters = output.get("parameters", []) if isinstance(output, dict) else []
    domain     = output.get("domain", "—") if isinstance(output, dict) else "—"

    # Index rapide url -> résultat (statut, etc.)
    results_by_url = {r.get("url"): r for r in results if isinstance(r, dict)}

    if not urls:
        return [Paragraph(f"Aucune URL avec paramètres trouvée pour {domain}.", styles["small"])]

    C_ACCENT  = colors.HexColor("#00e5a0")
    C_MUTED   = colors.HexColor("#6b6b78")
    C_BG      = colors.HexColor("#0d0d0f")
    C_SURFACE = colors.HexColor("#141416")
    C_BORDER  = colors.HexColor("#2a2a2e")
    C_TEXT    = colors.HexColor("#e8e8ec")
    C_HIGH    = colors.HexColor("#ff4d4d")
    C_MED     = colors.HexColor("#f5a623")

    flowables = []

    # Résumé des paramètres uniques
    if parameters:
        params_preview = ", ".join(parameters[:30])
        suffix = f" (+{len(parameters) - 30} autres)" if len(parameters) > 30 else ""
        flowables.append(Paragraph(
            f"<b>{len(parameters)} paramètre(s) unique(s)</b> : {params_preview}{suffix}",
            styles["body"]
        ))
        flowables.append(Spacer(1, 8))

    def _status_hex(code) -> str:
        if code is None:
            return "#6b6b78"
        if 200 <= code < 300:
            return "#00e5a0"
        if 300 <= code < 400:
            return "#f5a623"
        return "#ff4d4d"

    # Table des URLs (limitée pour ne pas exploser la taille du PDF)
    max_rows = 50
    data = [["URL", "Paramètres", "Statut"]]
    for url in urls[:max_rows]:
        parsed = urlparse(url)
        query_params = sorted(parse_qs(parsed.query).keys())
        short_url = url if len(url) <= 80 else url[:77] + "…"

        r = results_by_url.get(url, {})
        code = r.get("status_code")
        if r.get("error"):
            status_label = r["error"]
            status_color = "#ff4d4d"
        elif code is not None:
            status_label = str(code)
            status_color = _status_hex(code)
        else:
            status_label = "—"
            status_color = "#6b6b78"

        data.append([
            Paragraph(short_url, styles["mono_mut"]),
            Paragraph(", ".join(query_params), styles["small"]),
            Paragraph(f'<font color="{status_color}"><b>{status_label}</b></font>', styles["mono"]),
        ])  # type: ignore

    col_w = [page_width - 70*mm, 40*mm, 30*mm]
    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), C_SURFACE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), C_MUTED),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("TEXTCOLOR",     (0, 1), (-1, -1), C_TEXT),
        ("BACKGROUND",    (0, 1), (-1, -1), C_BG),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_BG, colors.HexColor("#161618")]),
        ("GRID",          (0, 0), (-1, -1), 0.4, C_BORDER),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flowables.append(tbl)

    if len(urls) > max_rows:
        flowables.append(Spacer(1, 6))
        flowables.append(Paragraph(
            f"… et {len(urls) - max_rows} URL(s) supplémentaire(s) non affichée(s) dans ce PDF.",
            styles["small"]
        ))

    return flowables