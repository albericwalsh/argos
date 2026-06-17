"""
entry.py — Module SQLMap
Argos Security Platform

Deux phases :
  Phase 1 — URLs (depuis ffuf) : teste chaque chemin découvert pour injection SQL
  Phase 2 — Services DB (depuis nmap) : teste les ports MySQL/PostgreSQL/MSSQL ouverts

Prérequis Docker :
  docker pull sqlmapproject/sqlmap
"""

import re
import json
import docker
from dataclasses import dataclass, field

DOCKER_IMAGE = "sqlmapproject/sqlmap"

# Ports de bases de données connues
DB_PORTS = {
    3306:  "mysql",
    5432:  "postgresql",
    1433:  "mssql",
    1521:  "oracle",
    27017: "mongodb",
    5984:  "couchdb",
    6379:  "redis",
}

# Services nmap considérés comme des DB
DB_SERVICE_NAMES = {"mysql", "postgresql", "ms-sql", "mssql", "oracle", "mongodb"}


@dataclass
class SQLMapResult:
    target_url:   str
    source:       str        # "url" | "db_service"
    vulnerable:   bool
    injections:   list[str]  = field(default_factory=list)
    databases:    list[str]  = field(default_factory=list)
    tables:       list[str]  = field(default_factory=list)
    output:       str        = ""
    error:        str        = ""
    method:       str        = "GET"   # GET | POST


# ── Normalisation ─────────────────────────────────────────────────────────────

def _to_dict(obj) -> dict:
    if isinstance(obj, dict): return obj
    if hasattr(obj, "__dict__"): return obj.__dict__
    return {}

def _normalize(raw) -> list[dict]:
    if not raw: return []
    if isinstance(raw, list): return [_to_dict(v) for v in raw]
    return [_to_dict(raw)]

def _normalize_target(target) -> str:
    """
    Accepte tous les formats de cible :
      - URL complète   "http://10.x.x.x:8081/index.php"  → retournée telle quelle
      - IP nue         "10.x.x.x"                        → retournée telle quelle
      - IP:port        "10.x.x.x:8081"                   → retournée telle quelle
      - hostname       "example.com"                      → retourné tel quel
      - liste          → premier élément
    """
    if not target: return ""
    if isinstance(target, list): target = target[0] if target else ""
    s = str(target).strip()
    if not s:
        return ""
    # URL complète avec schéma → on accepte directement
    if s.startswith(("http://", "https://")):
        return s
    # Tout le reste : IP nue, IP:port, IP:port/path, hostname, hostname/path
    # On préfixe http:// pour que sqlmap et les phases sachent que c'est une URL
    if "/" in s or ":" in s or re.match(r'^[a-zA-Z0-9]', s):
        return "http://" + s
    return ""

def _bool(val) -> bool:
    if isinstance(val, bool): return val
    return str(val).lower() in ("true", "1", "yes")


# ── Docker ────────────────────────────────────────────────────────────────────

def _run_sqlmap(client, args: list[str]) -> str:
    """Lance sqlmap avec les args donnés et retourne stdout+stderr."""
    cmd = ["python", "/sqlmap/sqlmap.py", "--batch", "--no-cast"] + args
    try:
        out = client.containers.run(
            image        = DOCKER_IMAGE,
            command      = cmd,
            remove       = True,
            network_mode = "host",
            stdout       = True,
            stderr       = True,
        )
        return out.decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"


# ── Parsing de la sortie sqlmap ───────────────────────────────────────────────

def _parse_output(raw: str) -> tuple[bool, list[str], list[str], list[str]]:
    """
    Retourne (vulnerable, injections, databases, tables) depuis la sortie sqlmap.
    """
    vulnerable  = False
    injections  = []
    databases   = []
    tables      = []

    for line in raw.splitlines():
        line_s = line.strip()

        # Injection trouvée
        if "is vulnerable" in line_s.lower() or "sqlmap identified the following injection" in line_s.lower():
            vulnerable = True
        if "parameter:" in line_s.lower() and ("injectable" in line_s.lower() or "type:" in line_s.lower()):
            vulnerable = True

        # Type d'injection
        if line_s.startswith("Type:") or "    Type: " in line:
            inj = line_s.replace("Type:", "").strip()
            if inj and inj not in injections:
                injections.append(inj)

        # Bases de données
        if re.match(r'\[\*\]\s+\w', line_s) and "available databases" not in line_s.lower():
            db = line_s.lstrip("[*] ").strip()
            if db and db not in databases and len(db) < 64:
                databases.append(db)

        # Tables
        if re.match(r'\| \w', line_s):
            tbl = line_s.strip("| ").strip()
            if tbl and tbl not in tables and len(tbl) < 64:
                tables.append(tbl)

    if databases:
        vulnerable = True

    return vulnerable, injections, databases, tables


# ── Phase 1 : URLs depuis ffuf ────────────────────────────────────────────────

def phase_urls(client, target: str, ffuf_results: list[dict],
               level: str, risk: str, forms: bool,
               dbs: bool, dump: bool,
               cookies: str, headers: str,
               data: str = "", method: str = "") -> list[SQLMapResult]:
    """
    Teste chaque URL découverte par ffuf (ou target directement).
    Si data est fourni (ex: "username=test&password=test"), envoie en POST
    et sqlmap tentera d'injecter sur chaque paramètre.
    Si forms=True, sqlmap crawle la page pour trouver les formulaires HTML.
    """
    results = []

    # Construit la liste d'URLs à tester
    urls_to_test: list[tuple[str, int]] = []
    for r in ffuf_results:
        base_url = r.get("base_url", "")
        path     = r.get("path", "")
        status   = int(r.get("status", 0) or 0)

        if status not in (200, 301, 302, 403):
            continue
        if not base_url:
            if target.startswith(("http://", "https://")):
                base_url = target.rstrip("/")
            else:
                base_url = f"http://{target}"

        url = (base_url.rstrip("/") + "/" + path.lstrip("/")) if path else base_url
        urls_to_test.append((url, status))

    if not urls_to_test:
        # Fallback : si target est une URL complète, la tester directement
        if target.startswith(("http://", "https://")):
            urls_to_test = [(target, 200)]
        else:
            urls_to_test = [(f"http://{target}/", 200)]

    print(f"[sqlmap] Phase 1 : {len(urls_to_test)} URL(s) à tester")

    for url, status in urls_to_test:
        print(f"[sqlmap]   → {url} [{status}]")

        # Détermine méthode et données POST
        _method = (method or "").upper()
        _data   = data.strip() if data else ""

        # Si data fourni → POST explicite sur les paramètres donnés
        # Si forms → sqlmap crawle la page pour trouver les <form>
        # Si ni l'un ni l'autre → GET sur l'URL avec tentative d'injection dans les params
        args = ["-u", url, f"--level={level}", f"--risk={risk}", "--timeout=30"]

        if _data:
            args += ["--data", _data]
            if _method in ("POST", ""):
                args += ["--method", "POST"]
            print(f"[sqlmap]   mode POST data: {_data}")
        elif forms:
            args += ["--forms"]
            print(f"[sqlmap]   mode --forms (crawl formulaires)")
        else:
            print(f"[sqlmap]   mode GET params")

        if dbs:     args += ["--dbs"]
        if dump:    args += ["--dump"]
        if cookies: args += ["--cookie", cookies]
        if headers:
            for h in headers.splitlines():
                if h.strip():
                    args += ["--header", h.strip()]

        raw = _run_sqlmap(client, args)
        vulnerable, injections, databases, tables = _parse_output(raw)

        if vulnerable:
            print(f"[sqlmap]   ✓ VULNÉRABLE — injections: {injections} — DBs: {databases}")
        else:
            print(f"[sqlmap]   ✗ non vulnérable")

        results.append(SQLMapResult(
            target_url = url,
            source     = "url",
            vulnerable = vulnerable,
            injections = injections,
            databases  = databases,
            tables     = tables,
            output     = raw[:800],
        ))

    return results


# ── Phase 2 : services DB depuis nmap ────────────────────────────────────────

def phase_db_services(client, target: str, nmap_services: list[dict],
                      level: str, risk: str,
                      dbs: bool, dump: bool) -> list[SQLMapResult]:
    # Si target est une URL, extraire juste l'IP pour la connexion DB directe
    import urllib.parse as _urlparse
    if target.startswith(("http://", "https://")):
        parsed = _urlparse.urlparse(target)
        target = parsed.hostname or target
    """
    Pour chaque service DB détecté par nmap, tente une connexion directe SQLMap.
    Supporte MySQL, PostgreSQL, MSSQL.
    """
    results = []

    db_services = [
        svc for svc in nmap_services
        if (
            int(svc.get("port", 0) or 0) in DB_PORTS
            or any(n in (svc.get("name") or "").lower() for n in DB_SERVICE_NAMES)
        )
        and svc.get("state") == "open"
    ]

    if not db_services:
        print("[sqlmap] Phase 2 : aucun service DB détecté par nmap")
        return []

    print(f"[sqlmap] Phase 2 : {len(db_services)} service(s) DB détecté(s)")

    for svc in db_services:
        port     = int(svc.get("port", 0) or 0)
        svc_name = (svc.get("name") or DB_PORTS.get(port, "unknown")).lower()
        product  = svc.get("product", "")

        # Détermine le type de DB pour sqlmap
        if "mysql" in svc_name or port == 3306:
            dbms = "MySQL"
            url  = f"mysql://{target}:{port}/"
        elif "postgre" in svc_name or port == 5432:
            dbms = "PostgreSQL"
            url  = f"postgresql://{target}:{port}/"
        elif "mssql" in svc_name or "ms-sql" in svc_name or port == 1433:
            dbms = "Microsoft SQL Server"
            url  = f"mssql://{target}:{port}/"
        else:
            # Service DB non supporté directement
            print(f"[sqlmap]   → {svc_name}:{port} — non supporté en connexion directe")
            continue

        print(f"[sqlmap]   → {dbms} sur {target}:{port} ({product})")

        args = [
            "-d", url,
            f"--level={level}", f"--risk={risk}",
            f"--dbms={dbms}",
            "--timeout=15",
        ]
        if dbs:  args += ["--dbs"]
        if dump: args += ["--dump"]

        raw = _run_sqlmap(client, args)
        vulnerable, injections, databases, tables = _parse_output(raw)

        if vulnerable:
            print(f"[sqlmap]   ✓ VULNÉRABLE — DBs: {databases}")
        else:
            print(f"[sqlmap]   ✗ non vulnérable / accès refusé")

        results.append(SQLMapResult(
            target_url = f"{dbms}://{target}:{port}",
            source     = "db_service",
            vulnerable = vulnerable,
            injections = injections,
            databases  = databases,
            tables     = tables,
            output     = raw[:800],
        ))

    return results


# ── Print ─────────────────────────────────────────────────────────────────────

def print_results(results: list[SQLMapResult]) -> None:
    vuln = [r for r in results if r.vulnerable]
    print(f"\n{'SOURCE':<12} {'URL/SERVICE':<50} {'VULNÉRABLE':<12} DBs")
    print("-" * 100)
    for r in results:
        dbs_str = ", ".join(r.databases[:3]) or "—"
        flag    = "✓ OUI" if r.vulnerable else "✗ non"
        print(f"{r.source:<12} {r.target_url[:48]:<50} {flag:<12} {dbs_str}")
    print()
    print(f"[sqlmap] {len(vuln)}/{len(results)} cible(s) vulnérable(s) à l'injection SQL.")
    if vuln:
        all_dbs = set(db for r in vuln for db in r.databases)
        if all_dbs:
            print(f"[sqlmap] Bases trouvées : {', '.join(all_dbs)}")


# ── Point d'entrée Argos ──────────────────────────────────────────────────────

def main(args: dict) -> list[SQLMapResult]:
    """
    args:
      target   : str   — IP/domaine cible
      urls     : list  — sortie ffuf (SubProcessResult)
      services : list  — sortie nmap (Service)
      level    : str   — 1-5 (défaut 1)
      risk     : str   — 1-3 (défaut 1)
      forms    : bool  — tester les formulaires
      dbs      : bool  — énumérer les DBs
      dump     : bool  — dumper les tables
      cookies  : str   — cookie de session
      headers  : str   — headers additionnels
    """
    target   = _normalize_target(args.get("target", ""))
    level    = str(args.get("level",  1) or 1)
    risk     = str(args.get("risk",   1) or 1)
    forms    = _bool(args.get("forms", True))
    dbs      = _bool(args.get("dbs",   True))
    dump     = _bool(args.get("dump",  False))
    cookies  = str(args.get("cookies", "") or "")
    headers  = str(args.get("headers", "") or "")
    data     = str(args.get("data",    "") or "")   # ex: "username=test&password=test"
    method   = str(args.get("method",  "") or "")   # "GET" | "POST"

    ffuf_results  = _normalize(args.get("urls")     or [])
    nmap_services = _normalize(args.get("services") or [])

    if not target:
        print("[sqlmap] ERROR: target invalide.")
        return []

    print(f"[sqlmap] Cible    : {target}")
    print(f"[sqlmap] URLs     : {len(ffuf_results)}")
    print(f"[sqlmap] Services : {len(nmap_services)}")
    print(f"[sqlmap] Level={level}  Risk={risk}  Forms={forms}  DBs={dbs}  Dump={dump}")

    client = docker.from_env()

    # Phase 1 — URLs ffuf
    print("\n[sqlmap] ══ PHASE 1 : injection sur URLs ══")
    results_url = phase_urls(
        client, target, ffuf_results,
        level, risk, forms, dbs, dump, cookies, headers,
        data=data, method=method,
    )

    # Phase 2 — Services DB nmap
    print("\n[sqlmap] ══ PHASE 2 : services base de données ══")
    results_db = phase_db_services(
        client, target, nmap_services,
        level, risk, dbs, dump
    )

    all_results = results_url + results_db
    print_results(all_results)
    return all_results