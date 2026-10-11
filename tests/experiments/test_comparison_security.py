"""Comparison has no authority to recreate evidence or execute a workload."""

import builtins
import importlib.metadata
import io
import json
import os
import shutil
import socket
import subprocess
import sys

import pytest

from apizr.cli import main
from apizr.experiments import environment, inputs, inspection, outputs, runner, worker
from apizr.experiments.comparison import compare_runs, diff_bytes
from apizr.experiments.comparison_reporting import diff_text
from apizr.experiments.history import show_run
from apizr.experiments.store import DEFAULT_STORE, publish

from .comparison_support import record, replace


def forbidden(*args, **kwargs):
    pytest.fail("diff attempted to recreate evidence or perform external I/O")


def forbid_external(monkeypatch):
    for module, names in [
        (subprocess, ("Popen", "run")),
        (socket, ("socket", "create_connection", "getaddrinfo")),
        (
            importlib.metadata,
            ("version", "distribution", "distributions", "packages_distributions"),
        ),
        (runner, ("run_experiment",)),
        (worker, ("main",)),
        (inspection, ("inspect_experiment",)),
        (inputs, ("fingerprint_input", "fingerprint_inputs")),
        (outputs, ("fingerprint_output", "fingerprint_outputs")),
        (environment, ("capture_runtime_environment",)),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        allowed = (sys.stdlib_module_names - {"pickle", "_pickle"}) | {
            "apizr",
            "pydantic",
            "pydantic_core",
            "typing_extensions",
            "annotated_types",
            "typing_inspection",
        }
        assert name.split(".")[0] in allowed
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_pure_comparison_zero_io(monkeypatch):
    a, b = record(), record(status="failed")
    expected = diff_bytes(compare_runs(a, b)), diff_text(compare_runs(a, b))
    with monkeypatch.context() as guard:
        forbid_external(guard)
        for module, names in [
            (builtins, ("open",)),
            (io, ("open",)),
            (os, ("open", "read", "listdir", "scandir", "stat", "lstat")),
        ]:
            for name in names:
                guard.setattr(module, name, forbidden)
        actual = compare_runs(a, b)
        assert (diff_bytes(actual), diff_text(actual)) == expected


@pytest.mark.parametrize("format_name", ["text", "json"])
@pytest.mark.parametrize("prefix", [False, True])
def test_cli_after_deletion_reads_only_store_and_relocation(
    tmp_path, capfd, monkeypatch, format_name, prefix
):
    a = record()
    b = record(status="cancelled", metrics=(), outputs=())
    store = tmp_path / DEFAULT_STORE
    for value in (a, b):
        publish(store, value.plan, value.run)
    for name in (
        a.plan.subject.reference,
        "data/train.csv",
        "data/validation.csv",
        "requirements.lock",
        "model.bin",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original evidence source")
        path.unlink()
    moved = tmp_path / "relocated"
    shutil.copytree(store, moved)
    monkeypatch.chdir(tmp_path)
    paths, observed = [], []
    real_open, real_read = os.open, os.read
    allowed_files = {v.run_digest + ".json" for v in (a, b)} | {
        v.plan_digest + ".json" for v in (a, b)
    }
    allowed_inodes = {
        p.stat().st_ino
        for root in (store, moved)
        for p in (root / "plans", root / "runs")
    }

    def open_store(path, flags, *args, **kwargs):
        # The existing store walks directory descriptors, then opens only
        # bounded canonical JSON. Directory traversal itself reads no evidence.
        if not flags & os.O_DIRECTORY:
            assert str(path) in allowed_files and kwargs.get("dir_fd") is not None
            assert os.fstat(kwargs["dir_fd"]).st_ino in allowed_inodes
        fd = real_open(path, flags, *args, **kwargs)
        if not flags & os.O_DIRECTORY:
            paths.append(str(path))
        return fd

    def read_store(fd, count):
        observed.append(count)
        return real_read(fd, count)

    selected = [v.run_digest[:12] if prefix else v.run_digest for v in (a, b)]
    with monkeypatch.context() as guard:
        forbid_external(guard)
        guard.setattr(builtins, "open", forbidden)
        guard.setattr(io, "open", forbidden)
        guard.setattr(os, "open", open_store)
        guard.setattr(os, "read", read_store)
        assert main(["experiment", "diff", *selected, "--format", format_name]) == 0
        first = capfd.readouterr()
        assert (
            main(
                [
                    "experiment",
                    "diff",
                    *selected,
                    "--store",
                    str(moved),
                    "--format",
                    format_name,
                ]
            )
            == 0
        )
        second = capfd.readouterr()
    assert first == second and not first.err
    assert paths and observed
    assert str(tmp_path) not in first.out
    assert a.run_digest in first.out and b.plan_digest in first.out


@pytest.mark.parametrize(
    "case", ["invalid", "missing", "ambiguous", "run", "plan", "binding", "exception"]
)
def test_cli_same_store_errors_no_partial_output(tmp_path, capfd, monkeypatch, case):
    from apizr.experiments import history

    a = record()
    publish(tmp_path, a.plan, a.run)
    identifier = a.run_digest
    if case == "invalid":
        identifier = "../secret"
    elif case == "missing":
        identifier = "f" * 64
    elif case == "ambiguous":
        identifier = identifier[:12]
        monkeypatch.setattr(history, "records", lambda path: iter([a, a]))
    elif case in {"run", "plan"}:
        folder = "runs" if case == "run" else "plans"
        next((tmp_path / folder).iterdir()).write_bytes(b"{}")
    elif case == "binding":
        from apizr.experiments import run_bytes, run_digest

        bad = replace(a.run, subject=replace(a.run.subject, digest="a" * 64))
        next((tmp_path / "runs").iterdir()).unlink()
        (tmp_path / "runs" / (run_digest(bad) + ".json")).write_bytes(run_bytes(bad))
    else:

        def broken(*args):
            raise OSError("secret exception")

        monkeypatch.setattr(history, "show_run", broken)
    assert (
        main(["experiment", "diff", a.run_digest, identifier, "--store", str(tmp_path)])
        == 2
    )
    out, err = capfd.readouterr()
    assert not out and "secret" not in err and str(tmp_path) not in err
    assert "apizr experiment diff:" in err


def test_cli_calls_existing_show_run_for_each_id(tmp_path, capfd, monkeypatch):
    from apizr.experiments import history

    a = record()
    publish(tmp_path, a.plan, a.run)
    calls = []

    def observed(path, run_id):
        calls.append((path, run_id))
        return show_run(path, run_id)

    monkeypatch.setattr(history, "show_run", observed)
    assert (
        main(
            [
                "experiment",
                "diff",
                a.run_digest,
                a.run_digest[:12],
                "--store",
                str(tmp_path),
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert calls == [(tmp_path, a.run_digest), (tmp_path, a.run_digest[:12])]
    assert json.loads(capfd.readouterr().out)["serving"] == "unknown"


@pytest.mark.parametrize(
    "args", [["--help"], ["experiment", "--help"], ["experiment", "diff", "--help"]]
)
def test_diff_help(args, capfd):
    if args == ["--help"]:
        assert main(args) == 0
    else:
        with pytest.raises(SystemExit) as exit_status:
            main(args)
        assert exit_status.value.code == 0
    assert "diff" in capfd.readouterr().out


def test_hashseed_and_filesystem_order_determinism(tmp_path):
    a, b = record(), record(status="failed")
    stores = [tmp_path / "first", tmp_path / "second"]
    for store, values in zip(stores, ((a, b), (b, a)), strict=True):
        for value in values:
            publish(store, value.plan, value.run)
    expected = None
    for seed, store in zip(
        ("1", "999999", "random"), (stores[0], stores[1], stores[0]), strict=True
    ):
        results = []
        for mode in ("json", "text"):
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "apizr.cli",
                    "experiment",
                    "diff",
                    a.run_digest,
                    b.run_digest,
                    "--store",
                    str(store),
                    "--format",
                    mode,
                ],
                env={**os.environ, "PYTHONHASHSEED": seed},
                capture_output=True,
                check=True,
                timeout=15,
            )
            assert not result.stderr
            results.append(result.stdout)
        if expected is None:
            expected = results
        assert results == expected
