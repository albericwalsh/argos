import os
import re
import json
import shutil
import dataclasses
from dataclasses import dataclass

import docker
from docker.errors import DockerException

DOCKER_IMAGE = "argos-hydra"  # image buildée localement depuis le Dockerfile fourni

# Ports par défaut par service (utilisés si non fournis et non trouvés via nmap)
DEFAULT_PORTS = {
    "ssh": 22, "ftp": 21, "telnet": 23, "smtp": 25, "pop3": 110,
    "imap": 143, "mysql": 3306, "mssql": 1433, "postgres": 5432,
    "rdp": 3389, "smb": 445, "vnc": 5900, "http-get": 80, "http-post-form": 80,
    "https-get": 443, "https-post-form": 443, "snmp": 161,
}

# Mapping nom de service nmap -> protocole hydra
NMAP_TO_HYDRA_SERVICE = {
    "ssh": "ssh", "ftp": "ftp", "telnet": "telnet", "smtp": "smtp",
    "pop3": "pop3", "imap": "imap", "mysql": "mysql", "ms-sql-s": "mssql",
    "postgresql": "postgres", "ms-wbt-server": "rdp", "microsoft-ds": "smb",
    "netbios-ssn": "smb", "vnc": "vnc", "http": "http-get", "https": "https-get",
    "snmp": "snmp",
}

# Services supportés par ce module (pour le scan automatique multi-services)
SUPPORTED_HYDRA_SERVICES = set(NMAP_TO_HYDRA_SERVICE.values())


@dataclass
class Credential:
    target:   str
    port:     int
    service:  str
    login:    str
    password: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Helpers accès dataclass-ou-dict (cohérent avec le module ffuf)
# ---------------------------------------------------------------------------

def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _svc_to_dict(svc) -> dict:
    if isinstance(svc, dict):
        return svc
    if dataclasses.is_dataclass(svc) and not isinstance(svc, type):
        return dataclasses.asdict(svc)
    if hasattr(svc, "__dict__"):
        return vars(svc)
    return {}


def _to_dict(obj):
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return obj


# ---------------------------------------------------------------------------
# Résolution target / services nmap
# ---------------------------------------------------------------------------

_TARGET_KEYS = ["target", "ip", "host", "address", "hostname", "ip_address"]


def _looks_like_service_list(value) -> bool:
    """Détecte si 'value' ressemble à une sortie nmap (list[Service|dict])."""
    if not isinstance(value, (list, tuple)) or not value:
        return False
    first = _to_dict(value[0])
    return isinstance(first, dict) and "port" in first and "name" in first


def resolve_target_and_services(raw_target):
    """
    Sépare la résolution en deux cas :
      - raw_target est un scalaire (IP/host) -> (host, [])
      - raw_target est une sortie nmap (list de services) -> on doit chercher
        l'host séparément (les Service nmap ne portent pas l'IP), donc on
        retourne (None, services) et l'appelant doit avoir 'target' ailleurs.
      - raw_target est une chaîne JSON -> désérialisée puis retraitée.
    """
    value = raw_target

    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped[0] in "[{":
            try:
                value = json.loads(stripped)
            except (ValueError, TypeError):
                pass

    if isinstance(value, (str, int, float)):
        sval = str(value).strip()
        return (sval if sval else None), []

    if _looks_like_service_list(value):
        return None, [_svc_to_dict(s) for s in value]

    if isinstance(value, dict):
        for k in _TARGET_KEYS:
            if k in value and value[k]:
                return str(value[k]).strip(), []

    return None, []


def services_to_hydra_jobs(services: list[dict]) -> list[dict]:
    """
    Convertit une liste de services nmap en jobs hydra :
      [{"service": "ssh", "port": 22}, {"service": "mysql", "port": 3306}, ...]
    Ne retient que les services supportés par Hydra (SUPPORTED_HYDRA_SERVICES).
    """
    jobs = []
    for svc in services:
        name = str(svc.get("name", "")).lower()
        port = svc.get("port")
        hydra_service = NMAP_TO_HYDRA_SERVICE.get(name)
        if hydra_service and port:
            jobs.append({"service": hydra_service, "port": port})
    return jobs


# ---------------------------------------------------------------------------
# Docker availability check (identique au pattern nikto/nmap)
# ---------------------------------------------------------------------------

def check_docker() -> tuple[bool, str]:
    if shutil.which("docker") is None:
        return False, (
            "Docker ne semble pas installé (binaire 'docker' introuvable dans le PATH). "
            "Installe Docker Desktop (Windows/macOS) ou Docker Engine (Linux)."
        )
    try:
        client = docker.from_env()
        client.ping()
    except DockerException as e:
        msg = str(e)
        if "CreateFile" in msg or "pipe" in msg.lower():
            return False, (
                "Docker est installé mais le daemon n'est pas joignable (pipe Windows introuvable). "
                "Lance Docker Desktop et attends qu'il affiche 'Running'."
            )
        if "Connection refused" in msg or "/var/run/docker.sock" in msg:
            return False, (
                "Docker est installé mais le daemon n'est pas lancé. "
                "Démarre le service avec 'sudo systemctl start docker' ou lance Docker Desktop."
            )
        return False, f"Docker est installé mais inaccessible : {msg}"
    except Exception as e:
        return False, f"Erreur inattendue lors de la vérification de Docker : {e}"

    # Vérifie que l'image locale existe (argos-hydra doit être buildée manuellement)
    try:
        client = docker.from_env()
        client.images.get(DOCKER_IMAGE)
    except docker.errors.ImageNotFound:
        return False, (
            f"L'image Docker '{DOCKER_IMAGE}' est introuvable en local. "
            f"Build-la d'abord avec :\n"
            f"  docker build -t {DOCKER_IMAGE} <chemin_vers_Dockerfile_hydra>\n"
            f"Le Dockerfile est fourni dans le dossier du module hydra."
        )
    except Exception as e:
        return False, f"Erreur lors de la vérification de l'image '{DOCKER_IMAGE}' : {e}"

    return True, "Docker est disponible."


def _resolve_target_for_docker(target: str) -> str:
    """Sur Docker Desktop, localhost à l'intérieur du container = le container."""
    if target in ("localhost", "127.0.0.1", "0.0.0.0"):
        return "host.docker.internal"
    return target


# ---------------------------------------------------------------------------
# Parsing sortie Hydra
# ---------------------------------------------------------------------------

# Ligne typique de succès Hydra :
# [22][ssh] host: 10.105.1.69   login: admin   password: admin123
_SUCCESS_RE = re.compile(
    r"\[(?P<port>\d+)\]\[(?P<service>[\w-]+)\]\s+host:\s+(?P<host>\S+)\s+"
    r"login:\s+(?P<login>\S*)\s+password:\s+(?P<password>.*)$"
)


def parse_hydra_output(output: str, fallback_target: str, fallback_port: int, fallback_service: str) -> list[Credential]:
    creds: list[Credential] = []
    for line in output.splitlines():
        line = line.strip()
        match = _SUCCESS_RE.search(line)
        if not match:
            continue
        creds.append(Credential(
            target   = match.group("host") or fallback_target,
            port     = int(match.group("port")) if match.group("port") else fallback_port,
            service  = match.group("service") or fallback_service,
            login    = match.group("login"),
            password = match.group("password"),
        ))
    return creds


def print_results(creds: list[Credential]) -> None:
    print(f"\n{'TARGET':<18} {'PORT':<7} {'SERVICE':<14} {'LOGIN':<20} PASSWORD")
    print("-" * 90)
    for c in creds:
        print(f"{c.target:<18} {c.port:<7} {c.service:<14} {c.login:<20} {c.password}")
    if not creds:
        print("Aucune combinaison login/mot de passe valide trouvée.")
    print()


# ---------------------------------------------------------------------------
# Docker runner
# ---------------------------------------------------------------------------

def _build_login_args(login: str, login_list: str, volumes: dict) -> list[str]:
    """Retourne les args hydra pour le login + met à jour 'volumes' si fichier."""
    if login_list:
        host_dir  = os.path.abspath(os.path.dirname(login_list))
        filename  = os.path.basename(login_list)
        container_path = f"/wordlists/logins/{filename}"
        volumes[host_dir] = {"bind": "/wordlists/logins", "mode": "ro"}
        return ["-L", container_path]
    if login:
        return ["-l", login]
    return []


def _build_password_args(password: str, password_list: str, volumes: dict) -> list[str]:
    """Retourne les args hydra pour le password + met à jour 'volumes' si fichier."""
    if password_list:
        host_dir  = os.path.abspath(os.path.dirname(password_list))
        filename  = os.path.basename(password_list)
        container_path = f"/wordlists/passwords/{filename}"
        volumes[host_dir] = {"bind": "/wordlists/passwords", "mode": "ro"}
        return ["-P", container_path]
    if password:
        return ["-p", password]
    return []


def run_hydra(client, target: str, service: str, port: int, login: str, login_list: str,
              password: str, password_list: str, http_path: str, extra_options: list[str]) -> str:
    docker_target = _resolve_target_for_docker(target)

    volumes: dict = {}
    cmd: list[str] = []

    cmd += _build_login_args(login, login_list, volumes)
    cmd += _build_password_args(password, password_list, volumes)

    if not any(flag in cmd for flag in ("-l", "-L")):
        print("[hydra] WARNING: aucun login/login_list fourni — Hydra utilisera son comportement par défaut (souvent vide/échec).")
    if not any(flag in cmd for flag in ("-p", "-P")):
        print("[hydra] WARNING: aucun password/password_list fourni — Hydra utilisera son comportement par défaut (souvent vide/échec).")

    cmd += ["-s", str(port)] if port else []
    cmd += extra_options

    service_arg = service
    if service in ("http-post-form", "https-post-form", "http-get-form", "https-get-form"):
        if not http_path:
            raise ValueError(
                f"[hydra] Le service '{service}' nécessite le paramètre 'http_path' "
                f"(ex: '/login:user=^USER^&pass=^PASS^:F=incorrect')."
            )
        service_arg = f"{service}\n{http_path}".replace("\n", "")  # hydra attend "service" + arg séparé
        cmd += [docker_target, service, http_path]
    else:
        cmd += [docker_target, service]

    print(f"[hydra] Lancement : hydra {' '.join(cmd)}")

    run_kwargs = dict(
        image       = DOCKER_IMAGE,
        command     = cmd,
        remove      = True,
        volumes     = volumes if volumes else None,
        extra_hosts = {"host.docker.internal": "host-gateway"},
    )

    try:
        logs = client.containers.run(**run_kwargs)
    except docker.errors.ContainerError as e:
        logs = e.stderr or b""

    return logs.decode("utf-8", errors="replace") if isinstance(logs, bytes) else str(logs)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main(args: dict) -> list[dict]:
    """
    Point d'entrée du module Hydra.

    Args attendus :
      target        : str | list[Service] — IP/host, ou sortie nmap (services)
      service        : str  — protocole hydra (ssh, ftp, mysql, http-post-form...)
                              optionnel si 'target' contient des services nmap
      port           : str  — port (optionnel, déduit sinon)
      login          : str  — login unique
      login_list     : str  — chemin hôte vers fichier de logins
      password       : str  — mot de passe unique
      password_list  : str  — chemin hôte vers fichier de mots de passe
      http_path      : str  — requis pour http-post-form / http-get-form
      options        : str  — options hydra supplémentaires

    Retourne : list[dict] — credentials valides trouvés (Credential.to_dict())
    """
    raw_target  = args.get("target")
    raw_service = args.get("service")
    port_in     = str(args.get("port", "")).strip()

    login         = str(args.get("login", "")).strip()
    login_list    = str(args.get("login_list", "")).strip()
    password      = str(args.get("password", "")).strip()
    password_list = str(args.get("password_list", "")).strip()
    http_path     = str(args.get("http_path", "")).strip()
    options       = args.get("options", "")

    if isinstance(options, list):
        extra_options = options
    elif isinstance(options, str) and options:
        extra_options = options.split()
    else:
        extra_options = []

    # --- Résolution de la cible ---
    target, services_from_target = resolve_target_and_services(raw_target)

    if not target:
        msg = (
            "Impossible de déterminer la cible ('target'). "
            "Fournis une IP/host directement via '$inputs.target'."
        )
        print(f"[hydra] ERROR: {msg}")
        raise ValueError(f"[hydra] {msg}")

    # --- Résolution du service ---
    # 'service' peut être :
    #   - un string vide/None -> on déduit depuis les services
    #   - un string valide ("ssh", "mysql"...) -> job unique
    #   - une liste de Service nmap (si le workflow passe '$step.output' par erreur ici)
    #     -> on extrait les jobs depuis cette liste
    services_from_service_arg = []
    service_in = ""

    if raw_service is None or (isinstance(raw_service, str) and not raw_service.strip()):
        service_in = ""  # pas fourni -> déduction automatique
    elif isinstance(raw_service, (list, tuple)) or (
        dataclasses.is_dataclass(raw_service) and not isinstance(raw_service, type)
    ):
        # liste de services nmap passée dans 'service' par erreur de workflow
        print("[hydra] INFO: 'service' reçoit une liste de services nmap — extraction automatique des jobs.")
        raw_list = raw_service if isinstance(raw_service, (list, tuple)) else [raw_service]
        services_from_service_arg = [_svc_to_dict(s) for s in raw_list]
    elif isinstance(raw_service, str):
        cleaned = raw_service.strip().lower()
        # Vérifie que c'est un vrai nom de service et pas la repr() d'une liste
        if cleaned.startswith("[") or cleaned.startswith("service("):
            # repr() d'une liste/dataclass passée comme string
            print("[hydra] INFO: 'service' contient une repr de liste — ignoré, déduction automatique.")
        else:
            service_in = cleaned

    # Fusionne les services trouvés
    all_services = services_from_target + services_from_service_arg

    # --- Construction des jobs ---
    jobs: list[dict] = []

    if service_in:
        # Service explicite -> un seul job
        port_val = int(port_in) if port_in.isdigit() else DEFAULT_PORTS.get(service_in, 0)
        jobs.append({"service": service_in, "port": port_val})

    elif all_services:
        # Déduction depuis les services nmap
        jobs = services_to_hydra_jobs(all_services)
        if not jobs:
            msg = (
                "Aucun service supporté par Hydra trouvé dans la sortie nmap. "
                f"Services supportés : {', '.join(sorted(SUPPORTED_HYDRA_SERVICES))}."
            )
            print(f"[hydra] ERROR: {msg}")
            raise ValueError(f"[hydra] {msg}")
        print(f"[hydra] {len(jobs)} service(s) à tester : "
              + ", ".join(f"{j['service']}:{j['port']}" for j in jobs))
    else:
        msg = (
            "Aucun 'service' fourni et aucun service nmap exploitable. "
            "Passe 'service' explicitement (ex: 'ssh') ou chaîne avec nmap via '$step.output' dans un paramètre dédié."
        )
        print(f"[hydra] ERROR: {msg}")
        raise ValueError(f"[hydra] {msg}")


    if not login and not login_list:
        print("[hydra] WARNING: ni 'login' ni 'login_list' fourni.")
    if not password and not password_list:
        print("[hydra] WARNING: ni 'password' ni 'password_list' fourni.")

    docker_ok, docker_msg = check_docker()
    if not docker_ok:
        print(f"[hydra] ERROR: {docker_msg}")
        raise RuntimeError(f"[hydra] Docker indisponible : {docker_msg}")

    client = docker.from_env()

    all_creds: list[Credential] = []
    for job in jobs:
        svc  = job["service"]
        port = job["port"]
        print(f"\n[hydra] --- Test du service '{svc}' sur le port {port} ---")
        try:
            raw_output = run_hydra(
                client, target, svc, port,
                login, login_list, password, password_list,
                http_path, extra_options,
            )
        except ValueError as e:
            print(f"[hydra] SKIP service '{svc}' : {e}")
            continue

        creds = parse_hydra_output(raw_output, fallback_target=target, fallback_port=port, fallback_service=svc)
        all_creds.extend(creds)

    print_results(all_creds)
    print(f"[hydra] {len(all_creds)} credential(s) valide(s) trouvé(s).")

    return [c.to_dict() for c in all_creds]


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 4:
        main({"target": sys.argv[1], "service": sys.argv[2], "login": "admin", "password": sys.argv[3]})
    else:
        print("Usage: python entry.py <target> <service> <password>")