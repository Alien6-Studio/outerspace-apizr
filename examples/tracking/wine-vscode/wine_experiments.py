"""Real Wine dataset, measured held-out scores and explicit local Apizr Runs."""

import csv
from pathlib import Path

from sklearn.datasets import load_wine
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier

from apizr import tracking

ROOT = Path(__file__).resolve().parent


def evaluate(max_depth: int, source: str = "wine_experiments.py") -> dict[str, float]:
    dataset = load_wine()
    data = ROOT / "wine.csv"
    with data.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([*dataset.feature_names, "cultivar"])
        writer.writerows(
            [*row, int(target)]
            for row, target in zip(dataset.data, dataset.target, strict=True)
        )
    train_x, test_x, train_y, test_y = train_test_split(
        dataset.data,
        dataset.target,
        test_size=0.3,
        stratify=dataset.target,
        random_state=42,
    )
    with tracking.session(root=ROOT, source=source):
        tracking.log_input("wine", "wine.csv")
        tracking.log_parameter("max_depth", max_depth)
        tracking.log_parameter("random_state", 42)
        model = DecisionTreeClassifier(max_depth=max_depth, random_state=42)
        model.fit(train_x, train_y)
        predicted = model.predict(test_x)
        metrics = {
            "accuracy": round(float(accuracy_score(test_y, predicted)), 4),
            "macro_f1": round(float(f1_score(test_y, predicted, average="macro")), 4),
        }
        for name, value in metrics.items():
            tracking.log_metric(name, value)
    return metrics


if __name__ == "__main__":
    for depth in (1, 3):
        print(f"max_depth={depth}: {evaluate(depth)}")
