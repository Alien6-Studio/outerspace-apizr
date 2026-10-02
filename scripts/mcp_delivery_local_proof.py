"""Installed stdio delivery refusal/status proof; no registry or native tool exists."""

import json
import runpy
import subprocess
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

from apizr.delivery_batch import BatchResult

# Fixture construction is SDK-free and contains no delivery implementation.
request = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "tests/batch_inputs.py")
)["request"]


async def exercise(root: Path):
    config = json.loads((root / "installed.json").read_text())
    installed_version = subprocess.check_output(
        [
            config["plugin_python"],
            "-I",
            "-B",
            "-c",
            "from importlib.metadata import version; print(version('outerspace-apizr-mcp'))",
        ],
        text=True,
    ).strip()
    assert installed_version == "0.4.2rc2"
    results = []
    for mode in ("auto", "legacy"):
        batch = request(root / ("delivery-" + mode), required=False)
        file = root / ("delivery-" + mode + ".json")
        file.write_text(batch.model_dump_json(by_alias=True))
        policy = Path(config["operator_policy"])
        original_policy = policy.read_bytes()
        target = StdioServerParameters(
            command=config["cli"],
            args=[
                "mcp",
                "serve",
                "--project",
                config["project"],
                "--operator-policy",
                str(policy),
                "--plugins-dir",
                config["store"],
                "--delivery-request",
                str(file),
            ],
            cwd=root,
            env={
                "APIZR_TEST_SECRET": "PRIVATE_PARENT_SECRET",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        async with Client(target, mode=mode, read_timeout_seconds=20) as client:
            assert (
                client.server_info is not None
                and client.server_info.version == installed_version
            )
            assert client.protocol_version == (
                "2025-11-25" if mode == "legacy" else "2026-07-28"
            )
            assert len((await client.list_tools()).tools) == 6
            initial = await client.call_tool("apizr_delivery_status", {})
            assert not initial.is_error
            value = BatchResult.model_validate_json(
                json.dumps(initial.structured_content)
            )
            assert all(o.state == "not_started" for o in value.outcomes)
            assert not Path(batch.evidence_root).exists()
            try:
                file.write_text("PRIVATE_CHANGED_REQUEST")
                policy.write_text("PRIVATE_CHANGED_POLICY")
                args = {
                    "expected_delivery_manifest_digest": value.delivery_manifest_digest.model_dump(
                        mode="json"
                    )
                }
                for operation in ("run", "resume"):
                    reply = await client.call_tool("apizr_delivery_" + operation, args)
                    assert not reply.is_error
                    failed = BatchResult.model_validate_json(
                        json.dumps(reply.structured_content)
                    )
                    assert failed.state == "failed" and failed.exit_code == 1
                    assert all(
                        o.diagnostic
                        == (
                            "transfer_failed"
                            if operation == "run"
                            else "remote_state_unconfirmed"
                        )
                        for o in failed.outcomes
                    )
                    assert (
                        "PRIVATE" not in reply.model_dump_json()
                        and config["store"] not in reply.model_dump_json()
                    )
                    status = await client.call_tool("apizr_delivery_status", {})
                    assert (
                        not status.is_error
                        and status.structured_content == reply.structured_content
                    )
                repeated = await client.call_tool("apizr_delivery_run", args)
                assert (
                    repeated.structured_content["error"]["code"]
                    == "delivery_evidence_invalid"
                )
            finally:
                policy.write_bytes(original_policy)
            results.append(
                {
                    "protocol": client.protocol_version,
                    "version": installed_version,
                    "initial": "not_started",
                    "run": "failed",
                    "resume": "failed",
                    "business_results": True,
                    "startup_capture": True,
                }
            )
    (root / "mcp-delivery-local.json").write_text(json.dumps(results, indent=2))
    print(
        "PASS installed MCP delivery schemas/status, immutable capture, typed managed refusals and version on both SDK protocols"
    )


if __name__ == "__main__":
    anyio.run(exercise, Path(sys.argv[1]).resolve())
