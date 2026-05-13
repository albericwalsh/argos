import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
import base64

import docker  # pip install docker
import json

DOCKER_IMAGE = "secsi/ffuf:latest"  # image légère avec ffuf, pas besoin de Dockerfile

@dataclass
class SubProcessResult:
    path: str
    status: str
    size: int
    words: int
    lines: int
    redirect: str

def decode_ffuf_path(value: str) -> str:
    try:
        return base64.b64decode(value).decode("utf-8")
    except Exception:
        return value
    
def parse_ffuf(output: str):

    results = []

    for line in output.splitlines():

        line = line.strip()

        if not line:
            continue

        try:

            item = json.loads(line)

            fuzz_raw = item.get("input", {}).get("FUZZ", "")
            fuzz = decode_ffuf_path(fuzz_raw)

            results.append(
                SubProcessResult(
                    path=fuzz,
                    status=item.get("status", ""),
                    size=item.get("length", 0),
                    words=item.get("words", 0),
                    lines=item.get("lines", 0),
                    redirect=item.get(
                        "redirectlocation",
                        ""
                    )
                )
            )

        except Exception as e:

            print(f"Failed parsing line: {e}")

    return results

def print_results(subprocess: list[SubProcessResult]) -> None:
    print("\n#-----------------------------------------")
    print("  > Résultats du scan :")
    print("#-----------------------------------------\n")
    for result in subprocess:
        print(f"  - Path: {result.path}")
        print(f"    Status: {result.status}")
        print(f"    Size: {result.size} bytes")
        print(f"    Words: {result.words}")
        print(f"    Lines: {result.lines}")
        if result.redirect:
            print(f"    Redirect: {result.redirect}")
        print()  # ligne vide entre les résultats

def main(ffuf_args: list[str]) -> list[SubProcessResult]:
    client = docker.from_env()
    target, wordlist = None, None
    for i, arg in enumerate(ffuf_args):
        if arg in ("-u", "--url"):
            if i + 1 < len(ffuf_args):
                target = ffuf_args[i + 1]
        elif arg in ("-w", "--wordlist"):
            if i + 1 < len(ffuf_args):
                wordlist = ffuf_args[i + 1]
    
    if not target:
        print("Target URL is required (use -u or --url)")
        return []
    if not wordlist:
        print("Wordlist is required (use -w or --wordlist)")
        return []
    # Lance le conteneur, attend la fin, récupère stdout — Docker le stoppe automatiquement
    volumes = {
        os.path.abspath("./data/ressources"): {
            "bind": "/wordlists",
            "mode": "ro"
        }
    }
    
    container = client.containers.run(
        image=DOCKER_IMAGE,
        command=[
            "-u", target,
            "-w", wordlist,
            "-json"
        ],
        volumes=volumes,
        remove=False,
        detach=True
    )

    result = container.wait()
    stdout = container.logs(stdout=True, stderr=False)
    stderr = container.logs(stdout=False, stderr=True)
    
    if stderr:
        print("Error from ffuf:")
        print(stderr.decode("utf-8"))

    json_output = stdout.decode("utf-8")

    container.remove()
    
    subprocess = parse_ffuf(json_output)
    print_results(subprocess)

    return subprocess

if __name__ == "__main__":
    import sys
    main(sys.argv[1:])