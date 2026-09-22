import json
import os
import subprocess
import sys

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from oci.helpers import IMAGE
from repository_interfaces.conftest import evidence

from apizr.cli import main
from apizr.execution.policy import ExecutionPolicy
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_interfaces.generator import render_repository_bundle

from .helpers import FILES, SELECTED


def command(tmp_path, transport="rest", backend="local-process"):
    root = tmp_path / "project"
    root.mkdir(exist_ok=True)
    (root / "sample.py").write_text("def run(x: int = 1): return x\n")
    output = tmp_path / "output"
    args = [
        "expose",
        "build",
        transport,
        str(root),
        "--interface",
        transport,
        "--execution-mode",
        backend,
        "--select",
        "python:sample:run",
        "--output-dir",
        str(output),
    ]
    return args, output


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("backend", ["local-process", "oci-container"])
def test_cli_governed_static_success(tmp_path, capfd, transport, backend):
    args, output = command(tmp_path, transport, backend)
    policy = tmp_path / "execution.json"
    policy.write_text(
        "{}"
        if backend == "local-process"
        else '{"schema_version":"apizr.execution/v2"}'
    )
    args += ["--execution-policy", str(policy)]
    if backend == "oci-container":
        args += ["--runtime-image", IMAGE.image, "--runtime-platform", IMAGE.platform]
    assert main(args) == 0
    text = capfd.readouterr().out
    assert "Configured backend: " + backend in text and "Capabilities: 1" in text
    assert (output / "execution/bundle.json").is_file()
    if backend == "oci-container":
        assert "Provider: docker-engine" in text


@pytest.mark.parametrize(
    "document,flags,code",
    [
        (b"{}", [], 0),
        (b"bad SECRET", [], 2),
        (b" " * 1048577, [], 2),
        (b'{"schema_version":"apizr.execution/v2"}', [], 2),
        (b"{}", ["--runtime-image", IMAGE.image], 2),
        (None, ["--runtime-platform", IMAGE.platform], 2),
        (b'{"subprocess":{"mode":"deny"}}', [], 1),
        (b'{"effects":{"require_known":["network"]}}', [], 1),
    ],
)
def test_cli_refusal_codes_transactionality(tmp_path, capfd, document, flags, code):
    args, output = command(tmp_path)
    if document is not None:
        policy = tmp_path / "policy.json"
        policy.write_bytes(document)
        args += ["--execution-policy", str(policy)]
    assert main([*args, *flags]) == code
    captured = capfd.readouterr()
    assert "SECRET" not in captured.err and "Traceback" not in captured.err
    if code:
        assert not output.exists() and not captured.out


def test_late_planning_failure_preserves_existing_output(tmp_path, monkeypatch):
    from apizr.execution.policy import PolicyRefused
    from apizr.governed_repository import embedding

    args, output = command(tmp_path)
    output.mkdir()
    (output / "sentinel").write_text("original")
    policy = tmp_path / "execution.json"
    policy.write_text("{}")

    def fail(*a, **kw):
        raise PolicyRefused("unsupported_control")

    monkeypatch.setattr(embedding, "worker_plan", fail)
    assert main([*args, "--execution-policy", str(policy)]) == 1
    assert {p.name: p.read_text() for p in output.iterdir()} == {"sentinel": "original"}


@settings(max_examples=8, deadline=None)
@given(st.permutations(tuple(FILES)), st.permutations(SELECTED), st.booleans())
def test_enumeration_selection_and_policy_canonicalization(paths, selected, oci):
    policy = (ExecutionPolicyV2 if oci else ExecutionPolicy)()
    kwargs = {
        "interface": "mcp",
        "execution_policy": policy,
        "runtime_image": IMAGE if oci else None,
    }
    first = evidence(
        FILES, selected=SELECTED, modes=(policy.backend,), interfaces=("mcp",)
    )
    other = evidence(
        {p: FILES[p] for p in paths},
        selected=selected,
        modes=(policy.backend,),
        interfaces=("mcp",),
    )
    assert render_repository_bundle(*first, **kwargs) == render_repository_bundle(
        *other, **kwargs
    )
    canonical = type(policy).model_validate_json(
        json.dumps(policy.model_dump(mode="json"), sort_keys=False, indent=3)
    )
    assert render_repository_bundle(*first, **kwargs) == render_repository_bundle(
        *first, **{**kwargs, "execution_policy": canonical}
    )


def test_generation_audit_and_relocation_without_backend(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        root.mkdir()
        (root / "selected.py").write_text("def run(x: int=1): return x\n")
        (root / "hostile.py").write_text('raise RuntimeError("PROJECT EXECUTED")\n')
        (root / "setup.py").write_text('raise RuntimeError("BUILD EXECUTED")\n')
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema_version":"apizr.execution/v2"}')
    probe = """import sys,os,importlib.util
from pathlib import Path
from apizr.cli import main
import apizr.execution.policy
import apizr.repository_execution.docker
roots=sys.argv[1:3]
def forbidden(*a,**kw): raise AssertionError("backend/package probe")
apizr.execution.policy.local_capabilities=forbidden
apizr.repository_execution.docker.RepositoryDockerProvider.probe=forbidden
importlib.util.find_spec=forbidden
def audit(event,args):
 if event in {"subprocess.Popen","os.system","os.posix_spawn","os.fork","socket.connect","socket.bind","socket.getaddrinfo"}: raise AssertionError(event)
 if event=="import" and args[0].split(".")[0] in {"selected","hostile","setup"}: raise AssertionError("source import")
 if event=="exec" and any(str(args[0].co_filename).startswith(root) for root in roots): raise AssertionError("source execution")
sys.addaudithook(audit)
for index,root in enumerate(roots):
 assert main(["expose","build","mcp",root,"--interface","mcp","--execution-mode","oci-container","--select","python:selected:run","--execution-policy",sys.argv[3],"--runtime-image",sys.argv[4],"--runtime-platform",sys.argv[5],"--output-dir",sys.argv[6+index]])==0
"""
    outputs = [tmp_path / "one", tmp_path / "two"]
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            probe,
            str(first),
            str(second),
            str(policy),
            IMAGE.image,
            IMAGE.platform,
            *map(str, outputs),
        ],
        env={
            **os.environ,
            "PATH": "/nonexistent",
            "DOCKER_HOST": "invalid://not-assessed",
        },
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode()

    def snapshot(root):
        return {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*")
            if p.is_file()
        }

    assert snapshot(outputs[0]) == snapshot(outputs[1])
    assert {p.name for p in first.iterdir()} == {
        "selected.py",
        "hostile.py",
        "setup.py",
    }
