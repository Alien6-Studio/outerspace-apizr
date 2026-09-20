import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.execution import ExecutionPolicy, PolicyRefused
from apizr.execution import planner as execution_planner
from apizr.execution.policy import BackendCapabilities
from apizr.generators.mcp import render as mcp_render
from apizr.generators.rest import render as rest_render
from apizr.governed.embedding import MODULES, runtime_files, source
from apizr.governed.runtime import GovernedRuntime, artifact
from apizr.inspection import inspect_source

from .helpers import SOURCE, bundle


@pytest.mark.parametrize(
    "render,document", [(rest_render, "openapi.json"), (mcp_render, "mcp-tools.json")]
)
def test_interface_bytes_and_rendering_are_independent_of_host(
    render, document, monkeypatch
):
    inspected = inspect_source(SOURCE, module_name="stable.module")
    direct = render(inspected, SOURCE)
    first = render(inspected, SOURCE, execution_policy=ExecutionPolicy())

    def unavailable():
        raise AssertionError("generation probed the runtime host")

    monkeypatch.setattr(execution_planner, "local_capabilities", unavailable)
    second = render(inspected, SOURCE, execution_policy=ExecutionPolicy())
    assert first == second
    assert first[document] == direct[document]
    assert "execution/bundle.json" not in direct
    assert b"outerspace-apizr" not in first["requirements.txt"]
    assert not any(
        "analyzer" in name or "notebook_transformr" in name for name in first
    )
    bridge = json.loads(first["execution/bundle.json"])
    assert bridge["schema_version"] == "apizr.execution-bundle/v1"
    assert len(bridge["capabilities"]) == len(inspected.capability_ir.capabilities)
    for name, expected in bridge["artifacts"].items():
        assert hashlib.sha256(first[name]).hexdigest() == expected["value"]


@pytest.mark.parametrize("render", [rest_render, mcp_render])
def test_generation_is_static_and_unsupported_policy_fails_closed(render, monkeypatch):
    import socket
    import subprocess

    raw = b'def f(x: int=print("never execute")): return x'
    inspected = inspect_source(raw, module_name="hostile")

    def forbidden(*args, **kwargs):
        pytest.fail("generation performed runtime activity")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr("builtins.print", forbidden)
    with pytest.raises(ValueError, match="conditional"):
        render(inspected, raw, execution_policy=ExecutionPolicy())
    raw = b'def f(x: int=1):\n    print("never execute")\n    return x'
    inspected = inspect_source(raw, module_name="hostile")
    render(inspected, raw, execution_policy=ExecutionPolicy())
    with pytest.raises(PolicyRefused):
        render(
            inspected,
            raw,
            execution_policy=ExecutionPolicy.model_validate(
                {"network": {"mode": "deny"}}
            ),
        )


def test_embedding_copies_one_execution_implementation():
    rendered = runtime_files("rest")
    for name in MODULES:
        if name in {"capabilities/types.py", "interfaces/schema.py"}:
            continue
        assert (
            rendered["apizr_governed/" + name]
            == source(name).replace("from apizr.", "from apizr_governed.").encode()
        )
    assert "inspect_source" not in rendered["apizr_governed/inspection.py"].decode()


@settings(max_examples=5, deadline=None)
@given(
    st.integers(1, 5000),
    st.lists(st.sampled_from(["LANG", "TZ", "APIZR_TEST_SECRET"]), max_size=5),
)
def test_governed_artifact_determinism_property(timeout, names):
    raw = b"def total(a: int, /, *, b: int=2): return a+b"
    inspected = inspect_source(raw, module_name="deterministic.module")
    policy = ExecutionPolicy.model_validate(
        {"limits": {"wall_time_ms": timeout}, "environment": {"allow": names}}
    )
    other = ExecutionPolicy.model_validate(
        {
            "environment": {"allow": list(reversed(names))},
            "limits": {"wall_time_ms": timeout},
        }
    )
    for render in [rest_render, mcp_render]:
        assert render(inspected, raw, execution_policy=policy) == render(
            inspected, raw, execution_policy=other
        )


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize(
    "path",
    [
        "execution/bundle.json",
        "execution/policy.json",
        "execution/plans/total.json",
        "execution/worker.py",
        "source/governed_sample.py",
        "capability-ir.json",
        "readiness.json",
    ],
)
def test_startup_rejects_missing_or_modified_artifacts(tmp_path, transport, path):
    root = bundle(tmp_path / "bundle", transport)
    target = root / path
    original = target.read_bytes()
    target.write_bytes(original + b"corrupted")
    with pytest.raises(RuntimeError, match="bundle unavailable or invalid"):
        GovernedRuntime(root, transport)
    target.unlink()
    with pytest.raises(RuntimeError, match="bundle unavailable or invalid"):
        GovernedRuntime(root, transport)


def test_startup_refuses_unavailable_host_and_path_escape(tmp_path, monkeypatch):
    root = bundle(tmp_path / "bundle", "rest")
    monkeypatch.setattr(
        "apizr.governed.runtime.local_capabilities",
        lambda: BackendCapabilities(available=False),
    )
    with pytest.raises(RuntimeError, match="bundle unavailable or invalid"):
        GovernedRuntime(root, "rest")
    for path in ["../private", "/private", "source/../private", "source\\private"]:
        with pytest.raises(ValueError):
            artifact(root, path)
    outside = tmp_path / "outside"
    outside.write_bytes(b"private")
    (root / "escape").symlink_to(outside)
    with pytest.raises(ValueError):
        artifact(root, "escape")


def test_snapshot_direct_bytes_against_committed_golden():
    # The original direct golden tests also regenerate and compare every hash in
    # their manifests. These anchors predate governed integration.
    root = Path(__file__).parents[1] / "fixtures"
    expected = {
        "rest/v1/apizr-rest.json": "32597062a49b112139741c04a1cd6b8172cdd02c33258f91b032b9229cd8274c",  # gitleaks:allow -- public golden SHA-256, not a credential
        "mcp/v1/apizr-mcp.json": "2da79e379a56bd319275f3d5094421e86a7dc46974034683a6e0eb5e0810fc1f",  # gitleaks:allow -- public golden SHA-256, not a credential
    }
    for path, digest in expected.items():
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("transport", ["rest", "mcp"])
def test_fresh_governed_generation_has_no_source_import_network_or_worker(
    tmp_path, transport
):
    import subprocess
    import sys

    source_file = tmp_path / "hostile_target.py"
    marker = tmp_path / "executed"
    source_file.write_text(
        f"from pathlib import Path\ndef f(): Path({str(marker)!r}).touch()\n"
    )
    policy = tmp_path / "policy.json"
    policy.write_text("{}")
    output = tmp_path / "output"
    probe = """import sys
def guard(event,args):
    if event in {"socket.connect","subprocess.Popen","os.system"}:
        raise AssertionError(event)
    if event=="import" and args[0]=="hostile_target":
        raise AssertionError("source imported during generation")
    if event=="exec" and args[0].co_filename==sys.argv[1]:
        raise AssertionError("source executed during generation")
sys.addaudithook(guard)
from apizr.cli import main
raise SystemExit(main(["generate",sys.argv[4],sys.argv[1],"--output-dir",sys.argv[2],"--execution-policy",sys.argv[3]]))
"""
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            probe,
            str(source_file),
            str(output),
            str(policy),
            transport,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
