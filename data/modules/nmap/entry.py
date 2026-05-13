import xml.etree.ElementTree as ET
from dataclasses import dataclass

import docker  # pip install docker

DOCKER_IMAGE = "instrumentisto/nmap"  # image légère avec nmap, pas besoin de Dockerfile

@dataclass
class Service:
    port: int
    protocol: str
    state: str
    name: str
    product: str
    version: str

def parse_xml(xml_output: str) -> list[Service]:
    root = ET.fromstring(xml_output)
    services = []
    for host in root.findall("host"):
        ports = host.find("ports")
        if ports is None:
            continue
        for port in ports.findall("port"):
            state_el = port.find("state")
            svc_el   = port.find("service")
            portid   = port.get("portid")
            if portid is None:
                continue                        # port sans ID → on skip
            services.append(Service(
                port     = int(portid),
                protocol = port.get("protocol", "unknown"),
                state    = state_el.get("state", "unknown") if state_el is not None else "unknown",
                name     = svc_el.get("name", "")           if svc_el is not None else "",
                product  = svc_el.get("product", "")        if svc_el is not None else "",
                version  = svc_el.get("version", "")        if svc_el is not None else "",
            ))
    return services

def print_results(services: list[Service]) -> None:
    print(f"{'PORT':<8} {'PROTO':<6} {'ÉTAT':<12} {'SERVICE':<14} PRODUIT/VERSION")
    print("-" * 62)
    for s in services:
        label = f"{s.product} {s.version}".strip()
        print(f"{s.port:<8} {s.protocol:<6} {s.state:<12} {s.name:<14} {label}")

def main(nmap_args: list[str]) -> list[Service]:
    client = docker.from_env()

    # Lance le conteneur, attend la fin, récupère stdout — Docker le stoppe automatiquement
    output = client.containers.run(
        image      = DOCKER_IMAGE,
        command    = ["-oX", "-"] + nmap_args,  # XML vers stdout
        remove     = True,                       # équivalent --rm : stoppe + supprime après
        network_mode = "host",                   # accès réseau hôte pour le scan
    )

    xml_output = output.decode("utf-8")
    services   = parse_xml(xml_output)
    print_results(services)
    return services

if __name__ == "__main__":
    import sys
    main(sys.argv[1:])