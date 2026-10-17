"""Readable projections of actual Academy files; never manufacture engine output.

Copy this teaching tool beside the prepared fraud example. Product operations
are performed by the visible CLI commands; this tool projects their saved JSON.
A run-result summary is resolved through the installed CLI's read-only show.
The explicit prepare-holdout action loads the trusted model for SDK exercises.
"""

import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def read(path):
    return json.loads(Path(path).read_text())


def read_record(path):
    report = read(path)
    if report.get("schema_version") == "apizr.experiment-run-result/v1":
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "apizr.cli",
                "experiment",
                "show",
                report["run_digest"],
                "--format",
                "json",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    return report


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source(focus):
    notebook = read("fraud_detection.ipynb")
    code = "\n".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )
    if focus == "settings":
        for line in code.splitlines():
            if any(
                token in line
                for token in (
                    "n_estimators =",
                    "max_depth =",
                    "read_csv",
                    "test_size=",
                    "random_state=",
                    "stratify=",
                    "joblib.dump",
                    "if __name__",
                    "roc_auc =",
                    "precision =",
                    "recall =",
                )
            ):
                print(line.strip())
    elif focus in {"predict", "train"}:
        node = next(
            n
            for n in ast.parse(code).body
            if isinstance(n, ast.FunctionDef) and n.name == focus
        )
        first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        print("\n".join(code.splitlines()[first - 1 : node.end_lineno]))
    else:
        code = Path("thresholds.py").read_text()
        node = next(
            n
            for n in ast.parse(code).body
            if isinstance(n, ast.FunctionDef) and n.name == focus
        )
        first = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        print("\n".join(code.splitlines()[first - 1 : node.end_lineno]))


def inspection(path):
    report = read(path)
    print("ACTUAL INSPECTION (read-only projection)")
    print("Execution:", report["execution"])
    print("Source SHA:", report["code"]["source"]["digest"]["value"][:16])
    print("Section             Recorded state")
    for name, state in report["states"].items():
        print(f"{name:20}{state}")
    for item in report["data"]["artifacts"]:
        print("Input:", item["reference"], item["digest"][:16], item["size"], "bytes")
    for signal in report["parameters"]["signals"]:
        item = signal["parameter"]
        print("Static parameter:", item["name"], "=", item["value"])
    for diagnostic in report["data"]["diagnostics"]:
        print(
            "Data diagnostic:",
            diagnostic["code"],
            diagnostic.get("loader"),
            "line",
            diagnostic.get("line"),
        )
    print("Model exists:", Path("artifacts/model.joblib").exists())


def inspect_change():
    before, after = read("inspection-a.json"), read("inspection-b.json")
    print("ACTUAL INSPECTIONS: A -> B")
    print(
        "Notebook identity equal:", before["code"]["source"] == after["code"]["source"]
    )
    print("Static parameters equal:", before["parameters"] == after["parameters"])
    for report in (before, after):
        item = report["data"]["artifacts"][0]
        print("Active CSV:", item["reference"], "SHA", item["digest"][:16])
    print("A execution:", before["execution"], "B execution:", after["execution"])
    print("Observed metric values have not been created by these inspections.")


def run(path):
    record = read_record(path)
    plan, observed = record["plan"], record["run"]
    print("ACTUAL RETAINED RECORD", record["run_digest"][:16])
    print("Status:", observed["status"])
    print("Plan parameters:", {p["name"]: p["value"] for p in plan["parameters"]})
    print(
        "Run parameters:",
        {p["name"]: p["value"] for p in observed["effective_parameters"]},
    )
    for item in observed["metrics"]:
        print("Observed metric:", item["name"], "=", round(item["value"], 5))
    for item in observed["observed_inputs"]:
        print("Observed input:", item["reference"], item["digest"][:16])
    for item in observed["outputs"]:
        if item["name"] == "model":
            print(
                "Observed model:",
                item["reference"],
                item["digest"][:16],
                item["size"],
                "bytes",
            )
    print("Worker Python:", observed["environment"]["python_version"]["value"])
    print("Runtime seed observations:", len(observed["randomness"]))


def comparison(path):
    report = read(path)
    print("ACTUAL DIFF: material evidence / observed results")
    print("Material facets:", report["material_counts"])
    for item in report["data"]:
        print(
            "Data:",
            item["name"],
            "reference",
            item["reference_state"],
            "content",
            item["content_state"],
        )
    for item in report["parameters"]:
        print(
            "Parameter:",
            item["name"],
            "intended",
            item["planned_state"],
            "observed",
            item["observed_state"],
        )
    for item in report["metrics"]:
        print(
            "Metric:",
            item["name"],
            round(item["a"]["value"], 5),
            "->",
            round(item["b"]["value"], 5),
            "delta",
            round(item["delta"], 5),
        )


def retain():
    record = read_record("run-a.json")
    captured = record["run"]["observed_inputs"][0]
    print("Same path:", captured["reference"])
    print("Run A recorded SHA:", captured["digest"][:16])
    print("Current CSV SHA:   ", digest(captured["reference"])[:16])
    print("Same content now:  ", captured["digest"] == digest(captured["reference"]))
    print("History identifies A's bytes; it does not archive the full CSV/model.")


def binding():
    for interface in ("rest", "mcp"):
        report = read(f"bundles/{interface}/experiment-exposure.json")
        print(interface.upper(), "actual binding")
        binding = report.get("binding", report)
        print("Run:", binding["run_digest"][:16])
        print("Capability:", binding["capability"])
        for output in binding["outputs"]:
            print(
                "Selected output:",
                output["name"],
                output["reference"],
                output["digest"][:16],
            )
        print(
            "Training marker in bundle:",
            bool(list(Path(f"bundles/{interface}").rglob("trained.txt"))),
        )


def holdout():
    import joblib
    import pandas as pd
    from sklearn.model_selection import train_test_split

    frame = pd.read_csv("data/transactions.csv")
    columns = [
        "amount",
        "transaction_velocity",
        "foreign_transaction",
        "account_age_days",
    ]
    _, x_test, _, y_test = train_test_split(
        frame[columns].to_numpy(),
        frame["fraud"].to_numpy(),
        test_size=0.25,
        random_state=42,
        stratify=frame["fraud"],
    )
    model = joblib.load("artifacts/model.joblib")
    probabilities = model.predict_proba(x_test)[:, 1]
    with Path("evaluation.csv").open("w") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(("fraud", "probability"))
        writer.writerows(zip(y_test, probabilities, strict=True))
    print("Actual held-out rows:", len(y_test), "SHA", digest("evaluation.csv")[:16])
    print("Same synthetic split as the notebook; no final business threshold selected.")


def history():
    for path in sorted(Path(".apizr/experiments/v1/runs").glob("*.json")):
        record = read(path)
        print(
            "Run",
            path.stem[:12],
            "status",
            record["status"],
            "mode",
            record.get("capture", {}).get("mode", "cli"),
        )
        cell = record.get("capture", {}).get("cell")
        if cell:
            print("  cell:", cell["cell_id"], "execution:", cell["execution_count"])
        print(
            "  parameters:",
            {p["name"]: p["value"] for p in record["effective_parameters"]},
        )
        print(
            "  metrics:", {p["name"]: round(p["value"], 4) for p in record["metrics"]}
        )


def presentation():
    source, backup = Path("fraud_detection.ipynb"), Path("notebook-original.ipynb")
    if backup.exists():
        raise ValueError("Presentation backup already exists")
    backup.write_bytes(source.read_bytes())
    notebook = read(source)
    notebook["metadata"]["academy_presentation_note"] = (
        "Presentation change; no execution"
    )
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            cell["execution_count"] = 999
    source.write_text(json.dumps(notebook, indent=1) + "\n")
    print("Changed stored metadata/count only; code cell text is unchanged.")


def signal_check():
    before, after = read("inspection-b.json"), read("presentation.json")
    raw_same = before["code"]["source"]["digest"] == after["code"]["source"]["digest"]
    signal_same = before["code"]["signal_digest"] == after["code"]["signal_digest"]
    print("Actual raw notebook digest equal:", raw_same)
    print("Actual signal digest equal:", signal_same)
    print("Inspection execution:", after["execution"])
    assert not raw_same and signal_same
    Path("fraud_detection.ipynb").write_bytes(
        Path("notebook-original.ipynb").read_bytes()
    )


def refusal():
    print("Actual refusal (complete diagnostic retained in refused.log):")
    for line in Path("refused.log").read_text().strip().splitlines()[:3]:
        print(line[:100])


def failure_check():
    records = [read(p) for p in Path(".apizr/experiments/v1/runs").glob("*.json")]
    failed = [r for r in records if r["status"] == "failed"]
    assert len(failed) == 1
    assert "SYNTHETIC_WORKSHOP_EXCEPTION" not in json.dumps(failed[0])
    print("Actual failed capture retained:", failed[0]["status"])
    print("Exception message absent from the retained record: True")


def restore_model():
    Path("artifacts/model.joblib").write_bytes(
        Path("artifacts/original-model.joblib").read_bytes()
    )
    recorded = next(
        o for o in read_record("run-b.json")["run"]["outputs"] if o["name"] == "model"
    )
    assert digest("artifacts/model.joblib") == recorded["digest"]
    print("Selected model restored; recorded digest matches.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=(
            "source",
            "inspection",
            "inspect-change",
            "run",
            "comparison",
            "retain",
            "binding",
            "prepare-holdout",
            "history",
            "presentation",
            "signal-check",
            "refusal",
            "failure-check",
            "restore-model",
        ),
    )
    parser.add_argument("detail", nargs="?")
    args = parser.parse_args()
    actions = {
        "source": source,
        "inspection": inspection,
        "inspect-change": inspect_change,
        "run": run,
        "comparison": comparison,
        "retain": retain,
        "binding": binding,
        "prepare-holdout": holdout,
        "history": history,
        "presentation": presentation,
        "signal-check": signal_check,
        "refusal": refusal,
        "failure-check": failure_check,
        "restore-model": restore_model,
    }
    if args.action in {"source", "inspection", "run", "comparison"}:
        if args.detail is None:
            parser.error("This action requires an explicit source/report name")
        actions[args.action](args.detail)
    else:
        actions[args.action]()


if __name__ == "__main__":
    main()
