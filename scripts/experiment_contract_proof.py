"""Prove experiment contracts from an installed candidate outside the checkout."""

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import apizr.experiments as experiments
from apizr.experiments import (
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    SourceIdentity,
    capture_runtime_environment,
    discover_environment_specs,
    discover_inputs,
    discover_randomness,
    fingerprint_input,
    parse_input_declaration,
    plan_bytes,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)


def input_producer_proof() -> dict[str, object]:
    source = b'import pandas as pd\npd.read_csv("data/train.csv")\n'
    subject = SourceIdentity(
        kind="python",
        reference="train.py",
        digest=sha256(source).hexdigest(),
        capability_id="python:train:train",
    )
    discovery = discover_inputs(source, source_reference="train.py")
    assert discovery.artifacts[0].reference == "data/train.csv"
    declaration = parse_input_declaration("training=data/train.csv")
    with TemporaryDirectory(prefix="apizr-experiment-inputs-") as directory:
        root = Path(directory)
        (root / "data").mkdir()
        target = root / "data/train.csv"
        target.write_bytes(b"feature,label\n0.25,0\n")
        observed = fingerprint_input(root, declaration)
        assert not observed.diagnostics
        first = ExperimentPlan(
            subject=subject,
            execution=ExecutionIntent(kind="training"),
            inputs=observed.artifacts,
        )
        target.write_bytes(b"feature,label\n0.75,0\n")
        changed = fingerprint_input(root, declaration)
        second = ExperimentPlan(
            subject=subject, execution=first.execution, inputs=changed.artifacts
        )
        assert first.subject == second.subject
        assert first.inputs[0].reference == second.inputs[0].reference
        assert first.inputs[0].digest != second.inputs[0].digest
        assert plan_digest(first) != plan_digest(second)
        assert first.inputs[0].origin.value == "declared"
        assert first.inputs[0].content_origin is not None
        assert first.inputs[0].content_origin.value == "static"
        assert str(root).encode() not in plan_bytes(first)
        assert b"0.25" not in plan_bytes(first)
        return {
            "status": "passed",
            "plan_a": plan_digest(first),
            "plan_b": plan_digest(second),
            "capability_unchanged": True,
            "source_unchanged": True,
        }


def randomness_environment_proof() -> dict[str, object]:
    source = (
        "import numpy as np\n"
        "from sklearn.ensemble import RandomForestClassifier\n"
        "np.random.default_rng(42)\n"
        "RandomForestClassifier(random_state=42)\n"
    )
    result = discover_randomness(source, source_reference="train.py")
    assert not result.diagnostics
    assert len(result.controls) == 2
    assert result.relevant_distributions == ("numpy", "scikit-learn")
    subject = SourceIdentity(
        kind="python",
        reference="train.py",
        digest=sha256(source.encode()).hexdigest(),
        capability_id="python:train:train",
    )
    with TemporaryDirectory(prefix="apizr-experiment-environment-") as directory:
        root = Path(directory)
        content = b"version = 1\n"
        (root / "uv.lock").write_bytes(content)
        static = discover_environment_specs(root)
        observed = capture_runtime_environment(
            distributions=result.relevant_distributions, root=root
        )
        environment = observed.evidence
        assert environment.python_implementation is not None
        assert environment.python_version is not None
        assert environment.platform is not None
        assert environment.architecture is not None
        assert environment.python_implementation.value == sys.implementation.name
        assert environment.python_version.value == platform.python_version()
        assert environment.platform.value == sys.platform
        assert environment.architecture.value == platform.machine()
        packages = {package.name: package for package in environment.packages}
        assert set(packages) == {"numpy", "scikit-learn", "outerspace-apizr"}
        assert packages["outerspace-apizr"].version == importlib.metadata.version(
            "outerspace-apizr"
        )
        assert packages["outerspace-apizr"].origin.value == "runtime"
        assert all(
            packages[name].version is None and packages[name].origin.value == "unknown"
            for name in result.relevant_distributions
        )
        assert (
            static.evidence.artifacts[0].digest
            == environment.artifacts[0].digest
            == sha256(content).hexdigest()
        )
        assert environment.artifacts[0].size == len(content)
        assert environment.artifacts[0].origin.value == "runtime"
        assert environment.artifacts[0].content_origin is not None
        assert environment.artifacts[0].content_origin.value == "runtime"
        plan = ExperimentPlan(
            subject=subject,
            execution=ExecutionIntent(kind="training"),
            randomness=result.controls,
            environment=static.evidence,
        )
        run = ExperimentRun(
            plan_digest=plan_digest(plan),
            subject=subject,
            status="success",
            environment=environment,
        )
        validate_run_binding(run, plan)
        assert sha256(plan_bytes(plan)).hexdigest() == plan_digest(plan)
        assert sha256(run_bytes(run)).hexdigest() == run_digest(run)
        assert str(root).encode() not in plan_bytes(plan) + run_bytes(run)
        assert b"version = 1" not in plan_bytes(plan) + run_bytes(run)
        seed_b = plan.model_copy(
            update={
                "randomness": (
                    result.controls[0].model_copy(update={"value": 43}),
                    result.controls[1],
                )
            }
        )
        assert seed_b.subject == plan.subject and seed_b.inputs == plan.inputs
        assert plan_digest(seed_b) != plan_digest(plan)
        (root / "uv.lock").write_bytes(b"version = 2\n")
        lock_b = plan.model_copy(
            update={"environment": discover_environment_specs(root).evidence}
        )
        assert plan_digest(lock_b) != plan_digest(plan)
        return {
            "status": "passed",
            "environment": environment.model_dump(mode="json"),
            "plan": plan_digest(plan),
            "run": run_digest(run),
            "seed_b": plan_digest(seed_b),
            "lock_b": plan_digest(lock_b),
            "source_and_inputs_unchanged": True,
        }


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
            "sklearn",
            "torch",
            "tensorflow",
            "joblib",
            "pyarrow",
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
                "input_producer": input_producer_proof(),
                "randomness_environment_producer": randomness_environment_proof(),
            },
            indent=2,
        )
        + "\n"
    )
    print("PASS installed experiment contracts and exact golden bytes")


if __name__ == "__main__":
    main()
