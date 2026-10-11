"""CLI boundary, exit meanings, history presentation and inspect laziness."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.environment.extras import MissingExtra
from apizr.experiments.history import show_run
from apizr.experiments.store import DEFAULT_STORE


@pytest.mark.parametrize("format_name", ["text", "json"])
def test_cli_journey(tmp_path, capfd, monkeypatch, format_name):
    source = tmp_path / "train.py"
    source.write_text("score = 0.75\n")
    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "experiment",
                "run",
                "train.py",
                "--metric",
                "auc=score",
                "--format",
                format_name,
            ]
        )
        == 0
    )
    out, err = capfd.readouterr()
    assert "trusted user code" in err and "not a security sandbox" in err
    run_id = (
        json.loads(out)["run_digest"]
        if format_name == "json"
        else out.split("Run: ")[1].splitlines()[0]
    )
    assert len(run_id) == 64
    assert show_run(tmp_path / DEFAULT_STORE, run_id).run.metrics[0].value == 0.75
    assert main(["experiment", "list", "--format", format_name]) == 0
    out, err = capfd.readouterr()
    assert not err
    assert (
        (json.loads(out)["total"] == 1) if format_name == "json" else run_id[:12] in out
    )
    assert main(["experiment", "show", run_id, "--format", format_name]) == 0
    out, err = capfd.readouterr()
    assert not err and run_id in out
    if format_name == "json":
        assert json.loads(out)["run"]["status"] == "success"
    else:
        assert "runtime application not directly observed" in out


@pytest.mark.parametrize(
    "body,status",
    [
        ('raise RuntimeError("secret_text")', "failed"),
        ("raise KeyboardInterrupt", "cancelled"),
    ],
)
def test_failed_result_still_prints_full_persisted_id(tmp_path, capfd, body, status):
    source = tmp_path / "train.py"
    source.write_text(body)
    store = tmp_path / "custom"
    assert (
        main(
            [
                "experiment",
                "run",
                str(source),
                "--store",
                str(store),
                "--format",
                "json",
            ]
        )
        == 1
    )
    out, err = capfd.readouterr()
    assert "secret_text" not in out + err and str(tmp_path) not in out + err
    result = json.loads(out)
    assert len(result["run_digest"]) == 64 and result["status"] == status
    assert (
        main(["experiment", "show", result["run_digest"], "--store", str(store)]) == 0
    )
    assert capfd.readouterr().out.startswith(status.upper())


@pytest.mark.parametrize(
    "args",
    [
        ["run", "missing.py"],
        ["run", "missing.py", "--metric", "x=eval()"],
        ["run", "missing.py", "--timeout-ms", "0"],
        ["list", "--limit", "0"],
        ["show", "../secret"],
        ["show", "a" * 64],
    ],
)
def test_sanitized_invocation_errors(tmp_path, capfd, monkeypatch, args):
    monkeypatch.chdir(tmp_path)
    assert main(["experiment", *args]) == 2
    out, err = capfd.readouterr()
    assert not out
    assert str(tmp_path) not in err and "Traceback" not in err


def test_environment_options_mutually_exclusive():
    with pytest.raises(SystemExit) as error:
        main(["experiment", "run", "train.py", "--env", "A", "--inherit-environment"])
    assert error.value.code == 2


def test_help_explains_trust_boundary(capfd):
    with pytest.raises(SystemExit) as error:
        main(["experiment", "run", "--help"])
    assert error.value.code == 0
    out = capfd.readouterr().out
    assert "trusted user code" in out and "not a security sandbox" in out
    main(["--help"])
    out = capfd.readouterr().out
    assert all(
        text in out
        for text in [
            "experiment inspect",
            "experiment run",
            "experiment list",
            "experiment show",
        ]
    )


def test_missing_notebook_extra_is_actionable(tmp_path, monkeypatch, capfd):
    from apizr.experiments import runner

    def missing(*args, **kwargs):
        raise MissingExtra("Install outerspace-apizr[notebook]")

    monkeypatch.setattr(runner, "run_experiment", missing)
    assert main(["experiment", "run", str(tmp_path / "a.ipynb")]) == 2
    assert "outerspace-apizr[notebook]" in capfd.readouterr().err


def test_inspect_cli_never_imports_worker_or_runner(tmp_path):
    source = tmp_path / "train.py"
    source.write_text('raise RuntimeError("not executed")')
    code = """import sys
from apizr.cli import main
assert main(['experiment','inspect',sys.argv[1]]) == 0
assert not {'apizr.experiments.runner','apizr.experiments.worker','apizr.experiments.run_protocol','apizr.experiments.store','apizr.experiments.history'}.intersection(sys.modules)
"""
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(source)],
        check=True,
        cwd=tmp_path,
        capture_output=True,
    )


def test_run_does_not_rewrite_existing_gitignore(tmp_path):
    from apizr.experiments.runner import run_experiment

    hidden = tmp_path / ".apizr"
    hidden.mkdir()
    ignore = hidden / ".gitignore"
    ignore.write_bytes(b"/operator.json\n# keep this exactly\n")
    original = ignore.read_bytes()
    path = tmp_path / "train.py"
    path.write_text("pass")
    run_experiment(path)
    assert ignore.read_bytes() == original


def test_history_json_does_not_change_repository_catalog(tmp_path):
    from analysis_authorization import analysis_policy

    from apizr.experiments.runner import run_experiment
    from apizr.repository import catalog_bytes, scan

    path = tmp_path / "train.py"
    path.write_text("def predict(x: float) -> float:\n    return x\n")
    before = scan(tmp_path, operator_policy=analysis_policy(tmp_path))
    run_experiment(path)
    after = scan(tmp_path, operator_policy=analysis_policy(tmp_path))
    assert catalog_bytes(after) == catalog_bytes(before)
    assert [c.id for c in after.capabilities] == ["python:train:predict"]


@pytest.mark.parametrize("notebook", [False, True])
def test_installed_run_proof_body(notebook):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from experiment_run_proof import prove

    result = prove(notebook=notebook)
    assert result["status"] == "passed" and result["fresh_worker"]
