from dataclasses import dataclass

@dataclass
class DebugOutput:
    message: str
    value: str
    step: str = "debug_input"

def main(args: dict) -> list[DebugOutput]:
    print(f"[debug_input] args reçus : {args}")

    text  = args.get("text", "default")
    count = int(args.get("count", 3))

    outputs = []
    for i in range(count):
        item = DebugOutput(
            message=f"Item {i+1} généré depuis '{text}'",
            value=f"{text}_{i+1}",
        )
        print(f"[debug_input] output {i+1} : {item}")
        outputs.append(item)

    return outputs