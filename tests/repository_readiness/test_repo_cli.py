"""Repo-first orchestration, canonical parity and a real non-execution audit."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from apizr.cli import main
from apizr.repository_readiness import (
    RepositoryReadinessReport,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/repository_readiness/completion"


def test_single_discovery_and_reads_shared_even_if_source_changes(
    tmp_path, monkeypatch, capfd
):
    import apizr.graph.builder as builder
    import apizr.repository.discovery as discovery

    path = tmp_path / "a.py"
    original = b"def f(): return 1\ndef caller(): return f()\n"
    path.write_bytes(original)
    calls, reads = [], []
    discover, read, assemble = builder.discover, discovery.read_source, builder.assemble

    def counted_discovery(*args, **kwargs):
        calls.append(args[0])
        return discover(*args, **kwargs)

    def counted_read(*args, **kwargs):
        reads.append(args[2])
        return read(*args, **kwargs)

    def mutate_after_assembly(*args, **kwargs):
        catalog = assemble(*args, **kwargs)
        path.write_text('raise RuntimeError("changed after discovery")')
        return catalog

    monkeypatch.setattr(builder, "discover", counted_discovery)
    monkeypatch.setattr(discovery, "read_source", counted_read)
    monkeypatch.setattr(builder, "assemble", mutate_after_assembly)
    assert main(["readiness", str(tmp_path), "--report"]) == 0
    result = RepositoryReadinessReport.model_validate_json(capfd.readouterr().out)
    assert calls == [tmp_path] and reads == ["a.py"]
    assert len(result.assessments) == 2
    assert result.assessments[0].relationships.direct[0].target == "python:a:f"


@pytest.mark.parametrize(
    "policy_name", [None, "ungoverned", "governed-local", "isolated-oci", "impossible"]
)
def test_independent_artifact_cli_and_repo_cli_exact_parity(
    tmp_path, capfd, policy_name
):
    root = tmp_path / "repository"
    shutil.copytree(FIXTURE / "project", root)
    flags = []
    if policy_name:
        policy_path = (
            Path(__file__).parents[2] / f"examples/readiness/{policy_name}.json"
        )
        flags = ["--policy", str(policy_path)]
    root_flags = ["--source-root", "src", "--exclude-dir", "ignored"]
    status = main(["readiness", str(root), *root_flags, *flags, "--report"])
    actual = capfd.readouterr().out.encode()
    assert status in (0, 1)
    assert (
        main(["readiness", str(root), *root_flags, *flags, "--format", "json"])
        == status
    )
    assert capfd.readouterr().out.encode() == actual

    # Independently run the public scan and graph CLIs over the same stable source universe.
    assert main(["scan", str(root), *root_flags, "--catalog"]) == 0
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(capfd.readouterr().out)
    assert main(["graph", str(root), *root_flags, "--graph"]) == 0
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(capfd.readouterr().out)
    for output in [["--format", "json"], ["--report"]]:
        assert (
            main(
                [
                    "repository-readiness",
                    str(catalog_path),
                    str(graph_path),
                    *flags,
                    *output,
                ]
            )
            == status
        )
        assert capfd.readouterr().out.encode() == actual
    if policy_name is None:
        assert actual == (FIXTURE / "repo-default-report.json").read_bytes()


def test_repo_text_summary_details_and_help(tmp_path, capfd):
    (tmp_path / "a.py").write_text(
        "\n".join(f"def f{i}(): return {i}" for i in range(25))
    )
    assert main(["readiness", str(tmp_path)]) == 0
    short = capfd.readouterr().out
    assert (
        "Execution contract compatibility" in short
        and "Further declarations omitted" in short
    )
    assert main(["readiness", str(tmp_path), "--details"]) == 0
    long = capfd.readouterr().out
    assert "omitted" not in long and len(long) > len(short)
    assert "ready declarations satisfying this mode's control requirements: 25" in long
    assert main(["--help"]) == 0
    assert "apizr readiness ROOT" in capfd.readouterr().out


@pytest.mark.parametrize(
    "flags",
    [
        ["--source-root", ".."],
        ["--max-file-bytes", "0"],
        ["--max-source-files", "0"],
        ["--max-total-bytes", "0"],
        ["--max-entries", "0"],
        ["--max-depth", "0"],
        ["--max-ast-nodes", "0"],
        ["--max-relationships", "0"],
        ["--max-calls", "0"],
        ["--max-imports", "0"],
    ],
)
def test_invalid_scan_graph_bounds_fail_before_discovery(
    tmp_path, capfd, monkeypatch, flags
):
    import apizr.graph.builder as builder

    def forbidden(*args, **kwargs):
        raise AssertionError("discovery before validation")

    monkeypatch.setattr(builder, "discover", forbidden)
    assert main(["readiness", str(tmp_path), *flags]) == 2
    output = capfd.readouterr()
    assert not output.out and str(tmp_path) not in output.err


def test_inaccessible_or_invalid_policies_and_roots(tmp_path, capfd):
    assert main(["readiness", str(tmp_path / "missing")]) == 2
    assert "inaccessible" in capfd.readouterr().err
    policy = tmp_path / "policy.json"
    for content in [
        b"SENSITIVE !",
        b"\xff",
        b'{"execution":{"require_controls":["unknown_control"]}}',
    ]:
        policy.write_bytes(content)
        assert main(["readiness", str(tmp_path), "--policy", str(policy)]) == 2
        output = capfd.readouterr()
        assert not output.out and "SENSITIVE" not in output.err
    assert (
        main(["readiness", str(tmp_path), "--policy", str(tmp_path / "missing")]) == 2
    )
    assert "Traceback" not in capfd.readouterr().err
    with pytest.raises(SystemExit):
        main(["readiness", str(tmp_path), "--report", "--format", "json"])


@pytest.mark.parametrize(
    "bound,value",
    [
        ("--max-file-bytes", "1"),
        ("--max-source-files", "1"),
        ("--max-total-bytes", "1"),
        ("--max-entries", "1"),
        ("--max-depth", "1"),
        ("--max-ast-nodes", "1"),
        ("--max-relationships", "1"),
        ("--max-calls", "1"),
        ("--max-imports", "1"),
    ],
)
def test_bounds_preserve_upstream_diagnostics(tmp_path, capfd, bound, value):
    nested = tmp_path / "nested/deeper"
    nested.mkdir(parents=True)
    (nested / "a.py").write_text("import math\nimport sys\ndef f():\n f(); f()\n")
    (tmp_path / "b.py").write_text("def g(): return 1\n")
    assert main(["readiness", str(tmp_path), bound, value, "--report"]) == 1
    report = RepositoryReadinessReport.model_validate_json(capfd.readouterr().out)
    assert report.catalog_diagnostics or report.graph_diagnostics


@given(
    st.permutations(["one", "two"]),
    st.permutations(["network_deny", "memory_limit", "pid_limit"]),
)
@settings(max_examples=12, deadline=None)
def test_canonical_checkout_location_and_option_order_determinism(roots, controls):
    # Exercise real CLI parsing as well as filesystem discovery across locations.
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        results = []
        for index, root_order in enumerate([roots, list(reversed(roots))]):
            root = base / f"unrelated-checkout-{index}"
            for name in ["one", "two"]:
                (root / name).mkdir(parents=True)
                (root / name / f"{name}.py").write_text("def f(): return 1\n")
            policy = base / f"policy-{index}.json"
            policy.write_text(
                json.dumps(
                    {
                        "execution": {
                            "modes": [
                                "oci-container",
                                "direct",
                                "local-process",
                                "direct",
                            ][:: 1 if index == 0 else -1],
                            "require_controls": list(controls)[
                                :: 1 if index == 0 else -1
                            ],
                        }
                    }
                )
            )
            command = [
                sys.executable,
                "-m",
                "apizr.cli",
                "readiness",
                str(root),
                "--report",
                "--policy",
                str(policy),
            ]
            for name in root_order:
                command.extend(["--source-root", name])
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=20,
                check=True,
                env={**os.environ, "PYTHONHASHSEED": str(index + 1)},
            )
            assert str(root).encode() not in result.stdout
            results.append(result.stdout)
        assert results[0] == results[1]


def test_repo_first_nonexecution_with_real_audit_hook(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
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
root=sys.argv[1]
def audit(event, args):
 if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.fork", "socket.connect", "socket.bind", "socket.getaddrinfo"}: raise AssertionError(event)
 if event == "import" and (args[0].split('.')[0] in {"hostile", "setup", "fastapi", "mcp", "docker"} or args[0].startswith(("apizr.oci.docker", "apizr.generators", "apizr.governed"))): raise AssertionError(args[0])
 if event == "exec" and str(args[0].co_filename).startswith(root): raise AssertionError("source execution")
 if event == "open" and isinstance(args[0], str) and args[0].startswith(root) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC): raise AssertionError("repository write")
sys.addaudithook(audit)
from apizr.cli import main
import apizr.readiness_cli
import apizr.execution.policy
import importlib.util
def forbidden(*args, **kwargs): raise AssertionError("runtime availability or package probe")
apizr.execution.policy.local_capabilities = forbidden
importlib.util.find_spec = forbidden
status = main(["readiness", root, "--report"])
assert status == 1
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
    assert (
        json.loads(result.stdout)["schema_version"] == "apizr.repository-readiness/v1"
    )
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
