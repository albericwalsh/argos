import requests
from dataclasses import dataclass
from time import sleep

NVD_API_CVE = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_API_CPE = "https://services.nvd.nist.gov/rest/json/cpes/2.0"

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

HEADERS = {"User-Agent": "Argos/1.0"}

@dataclass
class Vulnerability:
    cve_id: str
    service: str
    product: str
    version: str
    severity: str
    score: float
    description: str
    cpe: str = ""

# Mapping produit nmap -> keyword CPE plus précis
CPE_KEYWORDS = {
    "MySQL":                    "mysql mysql",
    "Microsoft Windows RPC":    "microsoft windows",
    "VMware Authentication Daemon": "vmware",
    "Node.js Express framework": "nodejs",
    "Microsoft Windows netbios-ssn": "microsoft windows",
}

def search_cpe(product: str, version: str) -> str | None:
    mapped = CPE_KEYWORDS.get(product, product)
    keyword = f"{mapped} {version}".strip()
    try:
        resp = requests.get(
            NVD_API_CPE,
            params={"keywordSearch": keyword, "resultsPerPage": 5},
            timeout=10,
            headers=HEADERS
        )
        if resp.status_code != 200:
            return None

        products = resp.json().get("products", [])
        if not products:
            return None

        # On prend le CPE le plus précis — si version dispo on le préfère
        for p in products:
            cpe_name = p.get("cpe", {}).get("cpeName", "")
            if version and version in cpe_name:
                return cpe_name

        # Sinon on prend le premier
        return products[0].get("cpe", {}).get("cpeName")

    except Exception as e:
        print(f"[vuln_lookup] Erreur CPE pour '{keyword}': {e}")
        return None

def query_nvd_by_cpe(cpe: str) -> list[dict]:
    """Cherche les CVEs associées à un CPE exact"""
    try:
        resp = requests.get(
            NVD_API_CVE,
            params={"cpeName": cpe, "resultsPerPage": 10},
            timeout=10,
            headers=HEADERS
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("vulnerabilities", [])
    except Exception as e:
        print(f"[vuln_lookup] Erreur CVE pour CPE '{cpe}': {e}")
        return []

def query_nvd_by_keyword(keyword: str) -> list[dict]:
    """Fallback si aucun CPE trouvé"""
    try:
        resp = requests.get(
            NVD_API_CVE,
            params={"keywordSearch": keyword, "resultsPerPage": 5},
            timeout=10,
            headers=HEADERS
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("vulnerabilities", [])
    except Exception as e:
        print(f"[vuln_lookup] Erreur keyword '{keyword}': {e}")
        return []

def parse_cve(cve_item: dict, service_name: str, product: str, version: str, cpe: str = "") -> Vulnerability | None:
    cve = cve_item.get("cve", {})
    cve_id = cve.get("id", "N/A")

    descs = cve.get("descriptions", [])
    description = next((d["value"] for d in descs if d["lang"] == "en"), "No description")

    metrics = cve.get("metrics", {})
    score = 0.0
    severity = "UNKNOWN"

    if "cvssMetricV31" in metrics:
        data = metrics["cvssMetricV31"][0]["cvssData"]
        score = data.get("baseScore", 0.0)
        severity = data.get("baseSeverity", "UNKNOWN")
    elif "cvssMetricV30" in metrics:
        data = metrics["cvssMetricV30"][0]["cvssData"]
        score = data.get("baseScore", 0.0)
        severity = data.get("baseSeverity", "UNKNOWN")
    elif "cvssMetricV2" in metrics:
        data = metrics["cvssMetricV2"][0]["cvssData"]
        score = data.get("baseScore", 0.0)
        severity = metrics["cvssMetricV2"][0].get("baseSeverity", "UNKNOWN")

    return Vulnerability(
        cve_id=cve_id,
        service=service_name,
        product=product,
        version=version,
        severity=severity,
        score=score,
        cpe=cpe,
        description=description[:120] + "..." if len(description) > 120 else description
    )

def print_results(vulns: list[Vulnerability]) -> None:
    if not vulns:
        print("Aucune vulnérabilité trouvée.")
        return

    print(f"\n{'CVE ID':<20} {'SCORE':<7} {'SÉVÉRITÉ':<10} {'SERVICE':<20} {'CPE':<40} DESCRIPTION")
    print("-" * 120)
    for v in vulns:
        cpe_short = v.cpe.split(":")[-3] + ":" + v.cpe.split(":")[-2] if v.cpe else "keyword fallback"
        print(f"{v.cve_id:<20} {v.score:<7} {v.severity:<10} {f'{v.product} {v.version}'.strip():<20} {cpe_short:<40} {v.description}")

def main(args: dict) -> list[Vulnerability]:
    services = args.get("services", [])
    min_severity = args.get("severity_filter", "MEDIUM").upper()
    min_level = SEVERITY_ORDER.get(min_severity, 1)

    if not services:
        print("[vuln_lookup] Aucun service fourni.")
        return []

    all_vulns = []
    seen_cves = set()  # évite les doublons

    for svc in services:
        if svc.state != "open" or not svc.product:
            continue

        product = svc.product
        version = svc.version

        # 1. Cherche le CPE exact
        print(f"[vuln_lookup] Recherche CPE pour: {product} {version}".strip())
        cpe = search_cpe(product, version)
        sleep(0.6)  # respect rate limit NVD (5 req/30s sans clé)

        if cpe:
            print(f"[vuln_lookup] CPE trouvé : {cpe}")
            raw = query_nvd_by_cpe(cpe)
        else:
            print(f"[vuln_lookup] Aucun CPE, fallback keyword: {product} {version}".strip())
            raw = query_nvd_by_keyword(f"{product} {version}".strip())

        sleep(0.6)

        for item in raw:
            vuln = parse_cve(item, svc.name, product, version, cpe or "")
            if vuln and vuln.cve_id not in seen_cves and SEVERITY_ORDER.get(vuln.severity, 0) >= min_level:
                all_vulns.append(vuln)
                seen_cves.add(vuln.cve_id)

    all_vulns.sort(key=lambda v: v.score, reverse=True)
    print_results(all_vulns)
    return all_vulns

# run service_vuln_scan {"target":"192.168.1.8","severity_filter":"HIGH"}