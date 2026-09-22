"""Real CLI behavior, one discovery, non-execution and sanitized refusals."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from apizr.cli import main
from apizr.exposure import ExposurePlan

FLAGS = ["--interface", "mcp", "--execution-mode", "oci-container"]
FIXTURE = Path(__file__).parents[1] / "fixtures/exposure/v1"


def test_inline_policy_canonical_parity_and_human_help(tmp_path, capfd):
    root = FIXTURE / "project"
    assert (
        main(
            [
                "expose",
                "plan",
                str(root),
                "--policy",
                str(FIXTURE / "policy.json"),
                "--plan",
            ]
        )
        == 0
    )
    assert capfd.readouterr().out.encode() == (FIXTURE / "plan.json").read_bytes()
    assert (
        main(
            [
                "expose",
                "plan",
                str(root),
                "--interface",
                "rest",
                *FLAGS,
                "--execution-mode",
                "local-process",
                "--select",
                "python:shop:calculate",
                "--select",
                "python:shop:availability",
                "--plan",
            ]
        )
        == 0
    )
    assert capfd.readouterr().out.encode() == (FIXTURE / "plan.json").read_bytes()
    assert main(["expose", "plan", str(root), *FLAGS]) == 0
    assert "Warning: empty selection" in capfd.readouterr().out
    assert (
        main(
            [
                "expose",
                "plan",
                str(root),
                *FLAGS,
                "--all-ready",
                "--exclude",
                "python:shop:helper",
            ]
        )
        == 0
    )
    text = capfd.readouterr().out
    assert "contract compatibility" in text and "Planned: 3" in text
    assert "python:shop:helper:" not in text
    assert main(["--help"]) == 0
    assert "apizr expose plan" in capfd.readouterr().out
    for args in (["expose", "--help"], ["expose", "plan", "--help"]):
        with pytest.raises(SystemExit) as error:
            main(args)
        assert error.value.code == 0


@pytest.mark.parametrize(
    "flags",
    [
        [],
        ["--interface", "mcp"],
        ["--execution-mode", "direct"],
        [*FLAGS, "--select", "f"],
        [*FLAGS, "--source-root", ".."],
        [*FLAGS, "--max-ast-nodes", "0"],
        [*FLAGS, "--require-control", "unknown"],
    ],
)
def test_invalid_policy_or_input_no_plan_no_source_fragments(tmp_path, capfd, flags):
    assert main(["expose", "plan", str(tmp_path), *flags, "--plan"]) == 2
    result = capfd.readouterr()
    assert not result.out and str(tmp_path) not in result.err


@pytest.mark.parametrize(
    "content", [b"SENSITIVE!", b"\xff", b"{}", b'{"interfaces":["grpc"]}']
)
def test_bad_policy_files(tmp_path, capfd, content):
    path = tmp_path / "policy.json"
    path.write_bytes(content)
    assert main(["expose", "plan", str(tmp_path), "--policy", str(path)]) == 2
    result = capfd.readouterr()
    assert (
        not result.out
        and "SENSITIVE" not in result.err
        and str(tmp_path) not in result.err
    )


def test_missing_files_mixed_inline_and_invalid_subcommands(tmp_path, capfd):
    for args in [
        ["--policy", str(tmp_path / "missing")],
        [*FLAGS, "--readiness-policy", str(tmp_path / "missing")],
        ["--policy", str(FIXTURE / "policy.json"), *FLAGS],
    ]:
        assert main(["expose", "plan", str(tmp_path), *args]) == 2
        assert not capfd.readouterr().out
    assert main(["expose", "plan", str(tmp_path / "missing"), *FLAGS]) == 2
    assert not capfd.readouterr().out
    for subcommand in ("build", "serve"):
        with pytest.raises(SystemExit) as error:
            main(["expose", subcommand])
        assert error.value.code == 2


@pytest.mark.parametrize(
    "flags,expected",
    [
        (["--select", "python:shop:typo"], "Unknown requested"),
        (["--select", "python:shop:unsupported"], "UNSUPPORTED"),
        (["--select", "python:shop:uncertain"], "CONDITIONAL"),
        (
            ["--select", "python:shop:uncertain", "--allow-conditional"],
            "interface contract",
        ),
        (
            [
                "--select",
                "python:shop:calculate",
                "--require-control",
                "subprocess_deny",
            ],
            "subprocess_deny",
        ),
        (["--max-ast-nodes", "1"], "Complete repository evidence"),
    ],
)
def test_cli_refusals_emit_diagnostics_only_stderr(capfd, flags, expected):
    assert (
        main(["expose", "plan", str(FIXTURE / "project"), *FLAGS, *flags, "--plan"])
        == 1
    )
    result = capfd.readouterr()
    assert (
        not result.out
        and expected in result.err
        and "Cannot create exposure plan" in result.err
    )


def test_separate_readiness_policy_and_conditional_optin(tmp_path, capfd):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.py").write_text("def f(): return 1")
    rp = tmp_path / "readiness.json"
    rp.write_text(
        json.dumps(
            {
                "effects": {"require_known": ["network"]},
                "execution": {"modes": ["direct"]},
            }
        )
    )
    args = [
        "expose",
        "plan",
        str(root),
        "--readiness-policy",
        str(rp),
        "--interface",
        "rest",
        "--execution-mode",
        "direct",
        "--select",
        "python:a:f",
    ]
    assert main(args) == 1
    capfd.readouterr()
    assert main([*args, "--allow-conditional", "--plan"]) == 0
    result = ExposurePlan.model_validate_json(capfd.readouterr().out)
    assert result.capabilities[0].compatible_execution_modes == ("direct",)
    assert result.capabilities[0].repository_readiness == "conditional"


def test_one_discovery_one_read_and_no_rescan_when_source_changes(
    tmp_path, monkeypatch, capfd
):
    import apizr.graph.builder as builder
    import apizr.repository.discovery as discovery

    path = tmp_path / "a.py"
    path.write_text("def f(): return 1\n")
    calls, reads = [], []
    discover, read, assemble = builder.discover, discovery.read_source, builder.assemble

    def counted_discovery(*args, **kwargs):
        calls.append(args[0])
        return discover(*args, **kwargs)

    def counted_read(*args, **kwargs):
        reads.append(args[2])
        return read(*args, **kwargs)

    def changed_after_assembly(*args, **kwargs):
        result = assemble(*args, **kwargs)
        path.write_text('raise RuntimeError("changed after discovery")')
        return result

    monkeypatch.setattr(builder, "discover", counted_discovery)
    monkeypatch.setattr(discovery, "read_source", counted_read)
    monkeypatch.setattr(builder, "assemble", changed_after_assembly)
    assert (
        main(
            [
                "expose",
                "plan",
                str(tmp_path),
                *FLAGS,
                "--select",
                "python:a:f",
                "--plan",
            ]
        )
        == 0
    )
    result = ExposurePlan.model_validate_json(capfd.readouterr().out)
    assert result.capability_ids() == ("python:a:f",)
    assert calls == [tmp_path] and reads == ["a.py"]


def test_real_audit_hook_forbids_execution_import_network_build_and_runtime_probes(
    tmp_path,
):
    root = tmp_path / "repository"
    root.mkdir()
    (root / "selected.py").write_text("def f(value: int) -> int: return value\n")
    (root / "hostile.py").write_text("""import socket, subprocess
open("TOP_LEVEL_MARKER", "w").write("executed")
socket.create_connection(("127.0.0.1", 9))
subprocess.run(["git", "status"])
@open("DECORATOR_MARKER", "w").write("executed")
def f(value=open("DEFAULT_MARKER", "w").write("executed")):
    return value
""")
    (root / "setup.py").write_text('raise RuntimeError("setup executed")')
    (root / "pyproject.toml").write_text(
        '[build-system]\nbuild-backend="hostile"\nrequires=[]'
    )
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    probe = """import os, sys
root = sys.argv[1]
def audit(event, args):
 if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "socket.connect", "socket.bind", "socket.getaddrinfo"}: raise AssertionError(event)
 if event == "import" and (args[0].split('.')[0] in {"selected", "hostile", "setup", "fastapi", "mcp", "docker"} or args[0].startswith(("apizr.oci.docker", "apizr.generators", "apizr.governed"))): raise AssertionError(args[0])
 if event == "exec" and str(args[0].co_filename).startswith(root): raise AssertionError("project execution")
 if event == "open" and isinstance(args[0], str) and args[0].startswith(root) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC): raise AssertionError("repository write")
sys.addaudithook(audit)
from apizr.cli import main
import apizr.exposure_cli
import apizr.execution.policy
import importlib.util
def forbidden(*args, **kwargs): raise AssertionError("runtime or package probe")
apizr.execution.policy.local_capabilities = forbidden
importlib.util.find_spec = forbidden
assert main(["expose", "plan", root, "--interface", "mcp", "--execution-mode", "oci-container", "--select", "python:selected:f", "--plan"]) == 0
assert not any(name.startswith(("fastapi", "mcp", "docker", "apizr.oci.docker", "apizr.generators", "apizr.governed")) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", probe, str(root)],
        cwd=root,
        env={
            **os.environ,
            "PATH": "/nonexistent",
            "DOCKER_HOST": "invalid://not-assessed",
        },
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert ExposurePlan.model_validate_json(result.stdout).capability_ids() == (
        "python:selected:f",
    )
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
