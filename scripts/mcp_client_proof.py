"""Real SDK stdio proof, executed by a separate installed client environment."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from apizr.compiler import assess_readiness, prepare_exposure
from apizr.exposure import ExposurePolicy
from apizr.exposure.serialization import plan_bytes
from apizr.graph import analyze_repository
from apizr.graph.serialization import graph_bytes
from apizr.project import load_project
from apizr.repository.serialization import catalog_bytes
from apizr.repository_readiness import RepositoryReadinessPolicy
from apizr.repository_readiness.serialization import report_bytes


def snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)): (
            "link:" + str(p.readlink())
            if p.is_symlink()
            else hashlib.sha256(p.read_bytes()).hexdigest()
        )
        for p in root.rglob("*")
        if p.is_symlink() or p.is_file()
    }


async def exercise(root: Path, mode: str):
    config = json.loads((root / "installed.json").read_text())
    project = Path(config["project"])
    settings = load_project(project)
    assert (
        settings.exposure_policy is not None and settings.readiness_policy is not None
    )
    policy = ExposurePolicy.model_validate_json(settings.exposure_policy.read_bytes())
    readiness = RepositoryReadinessPolicy.model_validate_json(
        settings.readiness_policy.read_bytes()
    )
    target = StdioServerParameters(
        command=config["cli"],
        args=[
            "mcp",
            "serve",
            "--project",
            str(project),
            "--plugins-dir",
            config["store"],
        ],
        cwd=root,
        env={
            "APIZR_TEST_SECRET": "must-not-be-inherited",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    async with Client(target, mode=mode, read_timeout_seconds=20) as client:
        assert client.protocol_version == (
            "2025-11-25" if mode == "legacy" else "2026-07-28"
        )
        tools = (await client.list_tools()).tools
        assert {t.name for t in tools} == {
            "apizr_analyze",
            "apizr_readiness",
            "apizr_plan_exposure",
        }
        assert all(
            t.annotations is not None
            and t.annotations.read_only_hint
            and t.input_schema["additionalProperties"] is False
            and t.output_schema
            for t in tools
        )
        analyzed = await client.call_tool("apizr_analyze", {})
        assert not analyzed.is_error, analyzed
        evidence = analyze_repository(
            settings.root, scan_policy=settings.scan, graph_policy=settings.graph
        )
        assert analyzed.structured_content["catalog"] == json.loads(
            catalog_bytes(evidence.catalog)
        )
        assert analyzed.structured_content["graph"] == json.loads(
            graph_bytes(evidence.graph)
        )
        scan_args = [
            str(settings.root),
            "--source-root",
            "src",
            "--exclude-dir",
            "ignored",
            "--max-file-bytes",
            "4096",
        ]
        for command, options, key in (
            ("scan", [*scan_args, "--catalog"], "catalog"),
            ("graph", [*scan_args, "--max-ast-nodes", "10000", "--graph"], "graph"),
        ):
            cli_result = subprocess.run(
                [config["cli"], command, *options],
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert cli_result.returncode in (0, 1)
            assert analyzed.structured_content[key] == json.loads(cli_result.stdout)
        assert "sources" not in analyzed.structured_content
        serialized = json.dumps(analyzed.structured_content)
        assert "outside_secret_value" not in serialized
        assert "must-not-be-inherited" not in serialized
        assert "dotenv-secret-value" not in serialized
        digest = analyzed.structured_content["repository_digest"]["value"]
        ready = await client.call_tool(
            "apizr_readiness", {"expected_repository_digest": digest}
        )
        assert not ready.is_error, ready
        report = assess_readiness(
            settings.root,
            scan_policy=settings.scan,
            graph_policy=settings.graph,
            readiness_policy=readiness,
        )
        assert ready.structured_content["report"] == json.loads(report_bytes(report))
        assert ready.structured_content["exit_code"] == report.exit_code
        cli_report = subprocess.run(
            [config["cli"], "readiness", "--project", str(project), "--report"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert cli_report.returncode == report.exit_code
        assert ready.structured_content["report"] == json.loads(cli_report.stdout)
        plan = await client.call_tool(
            "apizr_plan_exposure", {"expected_repository_digest": digest}
        )
        assert not plan.is_error, plan
        prepared = prepare_exposure(
            settings.root,
            scan_policy=settings.scan,
            graph_policy=settings.graph,
            readiness_policy=readiness,
            policy=policy,
        )
        assert plan.structured_content == json.loads(plan_bytes(prepared.plan))
        cli_plan = subprocess.run(
            [config["cli"], "expose", "plan", "--project", str(project), "--plan"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        assert plan.structured_content == json.loads(cli_plan.stdout)
        for args in (
            {"root": "/"},
            {"project": "/etc/passwd"},
            {"policy_file": "/secret"},
            {"expected_repository_digest": 123},
        ):
            refused = await client.call_tool("apizr_analyze", args)
            assert refused.is_error
        assert (
            await client.call_tool("apizr_plan_exposure", {"policy": {"unknown": True}})
        ).is_error
        proposed = policy.model_dump(mode="json")
        proposed["selection"]["include"] = ["python:calculator:missing"]
        refused = await client.call_tool("apizr_plan_exposure", {"policy": proposed})
        assert (
            refused.is_error
            and refused.structured_content["error"]["code"] == "exposure_refused"
        )
        # Startup policy bytes remain authoritative after these operator-side edits.
        original = settings.exposure_policy.read_bytes()
        settings.exposure_policy.write_text("invalid now")
        try:
            assert not (await client.call_tool("apizr_plan_exposure", {})).is_error
        finally:
            settings.exposure_policy.write_bytes(original)
        source = settings.root / "src/calculator.py"
        original = source.read_bytes()
        source.write_bytes(original + b"\n# changed repository\n")
        try:
            stale = await client.call_tool(
                "apizr_analyze", {"expected_repository_digest": digest}
            )
            assert (
                stale.is_error
                and stale.structured_content["error"]["code"] == "repository_changed"
            )
        finally:
            source.write_bytes(original)
        assert not (
            await client.call_tool(
                "apizr_analyze", {"expected_repository_digest": digest}
            )
        ).is_error
    print(
        f"PASS installed MCP stdio {mode}: schemas, canonical Python/CLI parity, refusals, frozen policy, digest guard, repeated calls and shutdown"
    )


async def boundary_errors(root: Path):
    config = json.loads((root / "installed.json").read_text())
    command = [config["cli"], "mcp", "serve", "--plugins-dir", config["store"]]
    invalid = root / "invalid.toml"
    invalid.write_text("not valid toml")
    for project in (root / "absent.toml", invalid):
        result = subprocess.run(
            [*command, "--project", str(project)],
            input=b"",
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 2 and result.stdout == b""
        assert b"startup_or_transport_refused" in result.stderr
    result = subprocess.run(
        [*command, "--project", config["project"]],
        input=b" " * 65537 + b"\n",
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2 and result.stdout == b""
    assert b"request_too_large" in result.stderr
    target = StdioServerParameters(
        command=config["cli"],
        args=[
            *command[1:],
            "--project",
            config["project"],
            "--max-response-bytes",
            "2048",
        ],
        cwd=root,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    async with Client(target, read_timeout_seconds=15) as client:
        large = await client.call_tool("apizr_analyze", {})
        assert (
            large.is_error and large.structured_content["error"]["code"] == "size_limit"
        )
        assert len((await client.list_tools()).tools) == 3
    absent_policy = root / "no-policy.toml"
    absent_policy.write_text('schema_version="apizr.project/v1"\nroot="project"\n')
    target = target.model_copy(
        update={"args": [*command[1:], "--project", str(absent_policy)]}
    )
    async with Client(target, read_timeout_seconds=15) as client:
        refused = await client.call_tool("apizr_plan_exposure", {})
        assert refused.structured_content["error"]["code"] == "policy_required"
        assert not (await client.call_tool("apizr_analyze", {})).is_error
    print(
        "PASS installed startup errors, wire/output bounds, missing policy, continued discovery"
    )


async def main(root: Path):
    project = root / "project"
    marker = root / "imported-project"
    (project / "src/trap.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
        "def safe_name(value: int) -> int:\n    return value\n"
    )
    (project / ".env").write_text("APIZR_TEST_SECRET=dotenv-secret-value\n")
    outside = root / "outside.py"
    outside.write_text("def outside_secret_value(): return 123\n")
    link = project / "src/escaped.py"
    if not link.is_symlink():
        link.symlink_to(outside)
    before = snapshot(project)
    await boundary_errors(root)
    for mode in ("auto", "legacy"):
        await exercise(root, mode)
    assert not marker.exists()
    assert snapshot(project) == before
    print(
        "PASS repository unchanged, import trap untouched, symlink boundary, no raw sources or environment secrets"
    )


if __name__ == "__main__":
    anyio.run(main, Path(sys.argv[1]))
