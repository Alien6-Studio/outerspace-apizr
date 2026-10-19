"""An admission refusal must be observable before the Docker handshake stage."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from qualification_scripts import implementation as qualification_script


@pytest.mark.parametrize("exit_code", [0, 2])
def test_early_core_exit_preserves_diagnostics_and_still_fails(
    tmp_path, monkeypatch, exit_code
):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "oci_smoke_diagnostics", str(qualification_script("smoke_oci_plugin"))
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module, "write_build_policy", lambda *args: tmp_path / "policy.json"
    )
    original = module.subprocess.Popen
    processes = []

    def start(*args, **kwargs):
        process = original(
            [
                sys.executable,
                "-I",
                "-c",
                f"import sys; print('unsupported_bundle_artifacts', file=sys.stderr); sys.exit({exit_code})",
            ],
            **kwargs,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(module.subprocess, "Popen", start)
    with pytest.raises(AssertionError, match="Core exited.*before Docker progress"):
        module.interrupt_build(
            sys.executable,
            {"docker": {"executable": sys.executable}},
            tmp_path,
            tmp_path,
            os.environ.copy(),
            None,
        )
    assert json.loads((tmp_path / "build-observation.json").read_bytes()) == {
        "phase": "interrupt_build",
        "state": "exited_before_progress",
        "exit_code": exit_code,
    }
    assert (
        "unsupported_bundle_artifacts"
        in (tmp_path / "build-diagnostic.log").read_text()
    )
    assert not (tmp_path / "docker-started.json").exists()
    assert processes[0].returncode == exit_code
    assert processes[0].stdout.closed and processes[0].stderr.closed
