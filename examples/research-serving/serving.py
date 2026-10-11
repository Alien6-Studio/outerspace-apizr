from features import normalize


def predict(value: float) -> float:
    return normalize(value) * 0.8
