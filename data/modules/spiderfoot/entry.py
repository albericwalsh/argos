import os
import docker
from dataclasses import dataclass
from src.variables import APP_DIR

DOCKER_IMAGE = "argos-spiderfoot"

@dataclass
class SpiderFootEvent:
    type: str
    source: str
    data: str
    timestamp: str = ""

def stream_logs(container):
    for line in container.logs(stream=True, follow=True):
        print("[SPIDERFOOT]", line.decode().rstrip())

def parse_args(args: list[str]):
    target = None
    modules = "all"

    i = 0
    while i < len(args):

        arg = args[i]

        if arg in ("--help", "-h"):
            print("Usage: --target \"example.com\" --modules sfp_dnsresolve")
            return None, None

        elif arg in ("--target", "-t"):
            target = args[i + 1].strip('"')
            i += 1

        elif arg in ("--modules", "-m"):
            modules = args[i + 1]
            i += 1

        i += 1

    return target, modules

def main(args):
    target, modules = parse_args(args)

    if not target:
        print("Target required")
        return []
    if not modules:
        modules = "all"

    client = docker.from_env()

    container = client.containers.run(
        image=DOCKER_IMAGE,
        command=["-s", target, "-m", modules],
        detach=True,
        remove=True
    ) # type: ignore[call-arg]

    stream_logs(container)

    return []