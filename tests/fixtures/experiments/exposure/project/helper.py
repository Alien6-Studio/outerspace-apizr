import json
from pathlib import Path

def _predict(value: int) -> int:
    model = json.loads(Path(__file__).with_name("model.json").read_text())
    return value * model["multiplier"]
