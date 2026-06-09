import json
import docker
from dataclasses import dataclass, field

DOCKER_IMAGE = "argos-spiderfoot"


@dataclass
class SpiderFootEvent:
    type:      str
    source:    str
    data:      str
    module:    str = ""
    timestamp: str = ""


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_output(raw: str) -> list[SpiderFootEvent]:
    """
    SpiderFoot -o JSON sort une liste d'objets JSON, un par ligne ou en bloc.
    Chaque objet a les clés : type, source, data, module, generated.
    """
    events = []

    # Tentative bloc JSON complet
    raw = raw.strip()
    if raw.startswith("["):
        try:
            items = json.loads(raw)
            for item in items:
                events.append(SpiderFootEvent(
                    type      = item.get("type", ""),
                    source    = item.get("source", ""),
                    data      = item.get("data", ""),
                    module    = item.get("module", ""),
                    timestamp = item.get("generated", ""),
                ))
            return events
        except Exception:
            pass

    # Fallback : JSON line-by-line
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            item = json.loads(line)
            events.append(SpiderFootEvent(
                type      = item.get("type", ""),
                source    = item.get("source", ""),
                data      = item.get("data", ""),
                module    = item.get("module", ""),
                timestamp = item.get("generated", ""),
            ))
        except Exception:
            pass

    return events


def print_results(events: list[SpiderFootEvent]) -> None:
    print(f"\n{'TYPE':<30} {'MODULE':<25} DATA")
    print("-" * 100)
    for e in events:
        print(f"{e.type:<30} {e.module:<25} {e.data[:60]}")
    if not events:
        print("  Aucun événement trouvé.")
    print()


# ── Point d'entrée Argos ──────────────────────────────────────────────────────

def main(args: dict) -> list[SpiderFootEvent]:
    """
    Appelé par le moteur Argos avec :
      {
        "target":  "example.com"   # IP, domaine, email, sous-réseau...
        "modules": "sfp_dnsresolve,sfp_ssl"   # optionnel, défaut = "all"
      }
    """
    target  = args.get("target",  "")
    modules = args.get("modules", "all") or "all"

    # Robustesse : le moteur peut injecter une liste
    if isinstance(target,  list): target  = target[0]  if target  else ""
    # modules peut être une liste ["sfp_googlesearch", "sfp_bing", ...] → joindre en CSV
    if isinstance(modules, list): modules = ",".join(str(m) for m in modules) if modules else "all"

    target  = str(target).strip()
    modules = str(modules).strip() or "all"

    if not target:
        print("[spiderfoot] ERROR: No target provided.")
        return []

    client = docker.from_env()

    print(f"[spiderfoot] Scan de '{target}' avec modules='{modules}'")

    container = client.containers.run(
        image        = DOCKER_IMAGE,
        command      = ["-s", target, "-m", modules, "-o", "json"],
        detach       = True,
        remove       = False,
        network_mode = "host",
    )

    # Stream des logs en temps réel
    for line in container.logs(stream=True, follow=True):
        decoded = line.decode().rstrip()
        if decoded:
            print(f"[spiderfoot] {decoded}")

    container.wait()
    stdout = container.logs(stdout=True, stderr=False).decode("utf-8")
    container.remove()

    events = parse_output(stdout)
    print_results(events)
    return events