from pathlib import Path
from typing import TypedDict
from helper import _predict

class PredictionInput(TypedDict):
    value: int

def predict(request: PredictionInput) -> dict[str, list[tuple[int, bool]]]:
    return {"predictions": [(_predict(request["value"]), True)]}

def train() -> str:
    return "private training helper"
