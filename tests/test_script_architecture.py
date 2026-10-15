"""Qualification ownership must fail on drift and preserve isolated CLI dispatch."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.qualification.ci import check_script_architecture as gate


def write_inventory(root, entries):
    groups = {
        "policy": {
            "kind": "domain",
            "prefix": "scripts/qualification/policy/",
            "responsibility": "Policy test gate.",
        },
        "composition": {
            "kind": "composition",
            "prefix": "scripts/",
            "responsibility": "Compose tooling.",
            "namespaces": ["scripts/__init__.py", "scripts/qualification/__init__.py"],
        },
    }
    lines = ["schema_version = 1"]
    for name, values in groups.items():
        lines.append(f'[groups."{name}"]')
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in values.items())
    for path, values in entries.items():
        lines.append(f'[files."{path}"]')
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in values.items())
    (root / "architecture").mkdir(exist_ok=True)
    (root / "architecture/scripts.toml").write_text("\n".join(lines) + "\n")


@pytest.fixture
def inventory(tmp_path):
    source = "scripts/qualification/policy/check_sample.py"
    for path in (
        "scripts/__init__.py",
        "scripts/qualification/__init__.py",
        "scripts/qualification/policy/__init__.py",
    ):
        p = tmp_path / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('"""Namespace."""\n')
    (tmp_path / source).write_text('"""Example bounded policy check."""\nVALUE = 1\n')
    (tmp_path / "scripts/check_sample.py").write_text(
        gate.facade("scripts.qualification.policy.check_sample", source, True)
    )
    workflow = tmp_path / ".github/workflows/check.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  gate:\n    steps:\n      - run: python -m scripts.qualification.policy.check_sample\n"
    )
    entries = {}
    for path, observed in gate.facts(tmp_path).items():
        namespace = path.endswith("/__init__.py")
        entry = {
            "group": "composition"
            if namespace and "/policy/" not in path
            else "policy",
            "kind": "namespace"
            if namespace
            else "compatibility"
            if path == "scripts/check_sample.py"
            else "implementation",
            "role": "check",
            "gate": "Test policy qualification.",
            **observed,
        }
        if entry["kind"] == "compatibility":
            entry.update(canonical=source, standalone=True)
        entries[path] = entry
    write_inventory(tmp_path, entries)
    assert gate.check(tmp_path)["result"] == "pass"
    return tmp_path, entries


def test_inventory_covers_the_real_repository():
    result = gate.check(Path(__file__).resolve().parents[1])
    assert result["files"] > 200
    assert result["compatibility_clis"] > 100


def test_new_unowned_script_is_rejected(inventory):
    root, _ = inventory
    (root / "scripts/new_operation.py").write_text("def operation(): pass\n")
    with pytest.raises(ValueError, match="ownership drift"):
        gate.check(root)


@pytest.mark.parametrize(
    "reference",
    ["python scripts/missing.py", "python -m scripts.qualification.policy.missing"],
)
def test_workflow_cannot_refer_to_absent_files_or_modules(inventory, reference):
    root, _ = inventory
    (root / ".github/workflows/check.yml").write_text(
        f"jobs:\n  gate:\n    steps:\n      - run: {reference}\n"
    )
    with pytest.raises(ValueError, match="Missing qualification"):
        gate.check(root)


@pytest.mark.parametrize(
    "field,value", [("workflows", []), ("ci_blocking", False), ("evidence", [])]
)
def test_recorded_calls_and_evidence_cannot_silently_drift(inventory, field, value):
    root, entries = inventory
    entries["scripts/qualification/policy/check_sample.py"][field] = value
    write_inventory(root, entries)
    with pytest.raises(ValueError, match="Stale"):
        gate.check(root)


def test_compatibility_cli_cannot_acquire_implementation(inventory):
    root, _ = inventory
    with (root / "scripts/check_sample.py").open("a") as stream:
        stream.write("\ndef extra_business_operation(): return 1\n")
    with pytest.raises(ValueError, match="facade contains implementation"):
        gate.check(root)


def test_namespace_cannot_acquire_operations(inventory):
    root, _ = inventory
    (root / "scripts/qualification/policy/__init__.py").write_text(
        "def run(): return 1\n"
    )
    with pytest.raises(ValueError, match="namespace contains operations"):
        gate.check(root)


def test_implementation_cannot_import_its_compatibility_command(inventory):
    root, _ = inventory
    (root / "scripts/qualification/policy/check_sample.py").write_text(
        "import check_sample\n"
    )
    with pytest.raises(ValueError, match="imports compatibility CLI"):
        gate.check(root)


def test_source_symlink_is_rejected_before_reading_target(inventory):
    root, _ = inventory
    source = root / "scripts/qualification/policy/check_sample.py"
    source.unlink()
    source.symlink_to(root / "not-created-private-input")
    with pytest.raises(ValueError, match="symlink"):
        gate.check(root)


def test_stable_isolated_cli_adds_no_checkout_to_import_paths(inventory, tmp_path):
    root, _ = inventory
    source = root / "scripts/qualification/policy/check_sample.py"
    source.write_text(
        "import sys\nfrom pathlib import Path\ncheckout=Path(__file__).resolve().parents[3]\nassert all(not Path(p).resolve().is_relative_to(checkout) for p in sys.path)\nraise SystemExit(7)\n"
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    result = subprocess.run(
        [sys.executable, "-I", str(root / "scripts/check_sample.py")],
        cwd=outside,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 7, result.stderr


def test_importable_compatibility_name_forwards_the_same_object(inventory):
    root, _ = inventory
    code = "import sys;sys.path.insert(0,sys.argv[1]);import scripts.check_sample as old;from scripts.qualification.policy import check_sample as new;assert old is new"
    subprocess.run(
        [sys.executable, "-I", "-c", code, str(root)],
        check=True,
        capture_output=True,
        timeout=10,
    )
