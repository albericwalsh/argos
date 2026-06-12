from dataclasses import dataclass
import requests

@dataclass
class whoisOutput:
    data: dict

def main(args: dict) -> whoisOutput:
    target = args.get("target")
    print(f"[whois] args reçus : {args}")

    try:
        resp = requests.get(f"https://rdap.org/domain/{target}", timeout=15, headers={"Accept": "application/json"})
        if resp.status_code != 200:
            print(f"[whois] Erreur HTTP : {resp.status_code}")
            return whoisOutput(data={})

        raw = resp.json()

        # Flatten the useful bits
        data = {
            "domain": raw.get("ldhName"),
            "status": raw.get("status", []),
            "nameservers": [ns.get("ldhName") for ns in raw.get("nameservers", [])],
        }

        for event in raw.get("events", []):
            action = event.get("eventAction")
            if action:
                data[f"event_{action}"] = event.get("eventDate")

        for entity in raw.get("entities", []):
            roles = entity.get("roles", [])
            handle = entity.get("handle")
            if handle:
                data[f"entity_{'_'.join(roles)}"] = handle

        data["_raw"] = raw

    except Exception as e:
        print(f"[whois] Erreur lors du parsing : {e}")
        return whoisOutput(data={})

    return whoisOutput(data=data)