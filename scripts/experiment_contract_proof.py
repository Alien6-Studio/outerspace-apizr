"""Prove experiment contracts from an installed candidate outside the checkout."""

import argparse
import importlib.util
import json
import sys
from hashlib import sha256
from pathlib import Path

import apizr.experiments as experiments
from apizr.experiments import (
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    SourceIdentity,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    imported = Path(experiments.__file__).resolve()
    assert not Path.cwd().resolve().is_relative_to(checkout)
    assert not imported.is_relative_to(checkout)
    assert all(not Path(item).resolve().is_relative_to(checkout) for item in sys.path)
    assert all(
        importlib.util.find_spec(name) is None
        for name in (
            "mcp",
            "fastapi",
            "apizr_mcp",
            "apizr_oci",
            "apizr_attest",
            "numpy",
            "pandas",
            "mlflow",
            "wandb",
            "dvc",
        )
    )
    source = SourceIdentity(kind="python", reference="train.py", digest="a" * 64)
    plan = ExperimentPlan(subject=source, execution=ExecutionIntent(kind="training"))
    run = ExperimentRun(plan_digest=plan_digest(plan), subject=source, status="success")
    validate_run_binding(run, plan)
    assert sha256(plan_bytes(plan)).hexdigest() == plan_digest(plan)
    assert sha256(run_bytes(run)).hexdigest() == run_digest(run)
    expected = json.loads((args.fixtures / "sha256.json").read_bytes())
    plan_raw = (args.fixtures / "plan.json").read_bytes()
    run_raw = (args.fixtures / "run.json").read_bytes()
    golden_plan = ExperimentPlan.model_validate_json(plan_raw)
    golden_run = ExperimentRun.model_validate_json(run_raw)
    validate_run_binding(golden_run, golden_plan)
    assert plan_bytes(golden_plan) == plan_raw
    assert run_bytes(golden_run) == run_raw
    goldens = {"plan": plan_digest(golden_plan), "run": run_digest(golden_run)}
    assert goldens == expected
    args.output.write_text(
        json.dumps(
            {
                "python": sys.version,
                "installed_from": str(imported),
                "outside_checkout": True,
                "optional_sdks_absent": True,
                "construction_binding_roundtrip": "passed",
                "goldens": goldens,
            },
            indent=2,
        )
        + "\n"
    )
    print("PASS installed experiment contracts and exact golden bytes")


if __name__ == "__main__":
    main()
