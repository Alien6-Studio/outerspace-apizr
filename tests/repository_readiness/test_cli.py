import os
import subprocess
import sys

import pytest

from apizr.graph import graph_bytes
from apizr.repository import catalog_bytes
from apizr.repository_readiness import RepositoryReadinessReport

from .test_readiness import artifacts


def command(*args):
    return subprocess.run(
        [sys.executable, "-m", "apizr.cli", "repository-readiness", *map(str, args)],
        capture_output=True,
    )


def test_cli_saved_artifacts_and_policy(tmp_path):
    c, g = artifacts()
    catalog = tmp_path / "catalog.json"
    graph = tmp_path / "graph.json"
    policy = tmp_path / "policy.json"
    catalog.write_bytes(catalog_bytes(c))
    graph.write_bytes(graph_bytes(g))
    result = command(catalog, graph, "--format", "json")
    assert result.returncode == 0
    assert (
        RepositoryReadinessReport.model_validate_json(result.stdout)
        .assessments[0]
        .state
        == "ready"
    )
    result = command(catalog, graph)
    assert result.returncode == 0 and b"not a runtime guarantee" in result.stdout
    policy.write_text('{"effects":{"require_known":["network"]}}')
    result = command(catalog, graph, "--policy", policy, "--format", "json")
    assert result.returncode == 1
    assert (
        RepositoryReadinessReport.model_validate_json(result.stdout)
        .assessments[0]
        .state
        == "conditional"
    )
    policy.write_text('{"execution":{"require_controls":["subprocess_deny"]}}')
    result = command(catalog, graph, "--policy", policy)
    assert result.returncode == 1 and b"UNSUPPORTED" in result.stdout


@pytest.mark.parametrize(
    "bad", [b"SENSITIVE_SOURCE !", b'{"schema_version":"wrong"}', b"\xff"]
)
def test_cli_errors_never_echo_input(tmp_path, bad):
    path = tmp_path / "bad.json"
    path.write_bytes(bad)
    result = command(path, path)
    assert result.returncode == 2
    assert not result.stdout and b"SENSITIVE" not in result.stderr
    assert command(path, tmp_path / "missing.json").returncode == 2


def test_framework_independent_import_and_host_independent_result():
    script = """
import sys
from apizr.repository_readiness import RepositoryReadinessPolicy, execution_compatibility
assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules for prefix in ('fastapi', 'mcp', 'apizr.generators', 'apizr.oci.docker'))
print(execution_compatibility(RepositoryReadinessPolicy().execution))
"""
    results = [
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            env={**os.environ, "DOCKER_HOST": host, "PYTHONHASHSEED": str(seed)},
            check=True,
        ).stdout
        for seed, host in [(1, "nonexistent://one"), (77, "nonexistent://two")]
    ]
    assert results[0] == results[1]


def test_cli_dispatch_in_process(tmp_path, capfd):
    from apizr.cli import main

    c, g = artifacts()
    catalog = tmp_path / "catalog.json"
    graph = tmp_path / "graph.json"
    policy = tmp_path / "policy.json"
    catalog.write_bytes(catalog_bytes(c))
    graph.write_bytes(graph_bytes(g))
    assert (
        main(["repository-readiness", str(catalog), str(graph), "--format", "json"])
        == 0
    )
    out = capfd.readouterr()
    assert (
        RepositoryReadinessReport.model_validate_json(out.out).assessments[0].state
        == "ready"
    )
    policy.write_text('{"effects":{"require_known":["network"]}}')
    assert (
        main(
            ["repository-readiness", str(catalog), str(graph), "--policy", str(policy)]
        )
        == 1
    )
    assert "CONDITIONAL" in capfd.readouterr().out
    policy.write_text("invalid")
    assert (
        main(
            ["repository-readiness", str(catalog), str(graph), "--policy", str(policy)]
        )
        == 2
    )
    assert "invalid or inaccessible" in capfd.readouterr().err
