import json
import os

import pytest

from apizr.execute_cli import main
from apizr.oci import entrypoint
from apizr.oci.model import ContainerResult


@pytest.mark.parametrize("names", [[], ["ALLOWED", "MISSING"]])
def test_entrypoint_clears_image_defaults_before_shared_worker(monkeypatch, names):
    monkeypatch.setattr(entrypoint.sys, "argv", ["entrypoint", *names])
    monkeypatch.setattr(os, "environ", {"IMAGE_DEFAULT": "secret", "ALLOWED": "passed"})
    calls = []
    monkeypatch.setattr(os, "chdir", lambda path: calls.append(path))
    monkeypatch.setattr(
        "apizr.execution.worker.main", lambda: calls.append(dict(os.environ))
    )
    entrypoint.main()
    assert calls == ["/bundle", {"ALLOWED": "passed"} if names else {}]


def test_cli_v2_explicit_identity_and_v1_stays_available(tmp_path, monkeypatch, capsys):
    source = tmp_path / "sample.py"
    source.write_text("def f(x:int): return x+1")
    policy = tmp_path / "policy.json"
    arguments = tmp_path / "args.json"
    arguments.write_text('{"x":2}')
    args = [str(source), "f", "--policy", str(policy), "--arguments", str(arguments)]
    policy.write_text('{"schema_version":"apizr.execution/v2"}')
    assert main(args) == 1  # Never guess a mutable image or platform.
    assert json.loads(capsys.readouterr().out)["status"] == "invalid_input"
    received = []

    def run(plan, raw, payload, **kwargs):
        received.append(plan)
        return ContainerResult(status="success", value=3)

    monkeypatch.setattr("apizr.oci.supervisor.execute", run)
    image_args = [
        "--runtime-image",
        "sha256:" + "0" * 64,
        "--runtime-platform",
        "linux/amd64",
    ]
    assert main([*args, *image_args]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "schema_version": "apizr.execution-result/v2",
        "status": "success",
        "value": 3,
    }
    assert received[0].policy.backend == "oci-container"
    policy.write_text("{}")
    assert main([*args, *image_args]) == 1
    capsys.readouterr()
    assert main(args) == 0
    assert (
        json.loads(capsys.readouterr().out)["schema_version"]
        == "apizr.execution-result/v1"
    )
