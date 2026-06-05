from dataclasses import dataclass

@dataclass
class DebugReport:
    total: int
    values: list[str]
    summary: str

def main(args: dict) -> DebugReport:
    print(f"[debug_output] args reçus : {args}")

    items = args.get("items", [])

    if not items:
        print("[debug_output] Aucun item reçu.")
        return DebugReport(total=0, values=[], summary="Rien reçu.")

    values = []
    for item in items:
        # compatible dict ou dataclass
        val = item.value if hasattr(item, "value") else item.get("value", str(item))
        values.append(val)
        print(f"[debug_output] item traité : {val}")

    summary = f"{len(values)} items reçus : {', '.join(values)}"
    print(f"[debug_output] summary : {summary}")

    return DebugReport(total=len(values), values=values, summary=summary)