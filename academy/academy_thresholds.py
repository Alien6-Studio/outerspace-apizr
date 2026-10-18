"""Teaching example: record threshold evaluation over a retained holdout sample."""

import argparse
import csv
from pathlib import Path

from apizr import tracking


def evaluate(threshold):
    with Path("evaluation.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    actual = [int(row["fraud"]) for row in rows]
    predicted = [float(row["probability"]) >= threshold for row in rows]
    tp = sum(bool(y) and p for y, p in zip(actual, predicted, strict=True))
    fp = sum(not y and p for y, p in zip(actual, predicted, strict=True))
    fn = sum(bool(y) and not p for y, p in zip(actual, predicted, strict=True))
    return {
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "flagged": sum(predicted),
    }


def session_example():
    with tracking.session(root=Path.cwd()) as capture:
        tracking.log_input("holdout", "evaluation.csv")
        tracking.log_parameter("threshold", 0.5)
        result = evaluate(0.5)
        for name, value in result.items():
            tracking.log_metric(name, value)
    print("Original return:", result)
    record = capture.record
    assert record is not None
    print("Retained Run:", record.run_digest)


@tracking.experiment(parameters=["threshold"], root=Path.cwd())
def tracked_evaluate(threshold):
    tracking.log_input("holdout", "evaluation.csv")
    result = evaluate(threshold)
    for name, value in result.items():
        tracking.log_metric(name, value)
    return result


@tracking.experiment(parameters=["threshold"], root=Path.cwd())
def failed_review(threshold):
    tracking.log_input("holdout", "evaluation.csv")
    tracking.log_metric("flagged", evaluate(threshold)["flagged"])
    raise ValueError("SYNTHETIC_WORKSHOP_EXCEPTION")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("session", "calls", "failure"))
    args = parser.parse_args()
    if args.action == "session":
        session_example()
    elif args.action == "failure":
        try:
            failed_review(0.5)
        except ValueError as error:
            assert str(error) == "SYNTHETIC_WORKSHOP_EXCEPTION"
            print("Original exception propagated:", type(error).__name__)
        else:
            raise AssertionError("The original exception was swallowed")
    else:
        for threshold in (0.35, 0.65):
            result = tracked_evaluate(threshold)
            assert result == evaluate(threshold), "Tracking changed the return value"
            print(f"threshold={threshold}: {result}")


if __name__ == "__main__":
    main()
