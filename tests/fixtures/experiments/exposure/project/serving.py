from pathlib import Path
from typing import TypedDict
from helper import _predict

class PredictionInput(TypedDict):
    value: int

def predict(request: PredictionInput) -> dict[str, list[tuple[int, bool]]]:
    return {"predictions": [(_predict(request["value"]), True)]}

def train() -> str:
    Path("model.json").write_text('{"multiplier": 3}')
    Path("debug.json").write_text('{"private": true}')
    return "private training helper"

if __name__ == "__main__":
    train()
