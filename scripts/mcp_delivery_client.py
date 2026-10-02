"""Installed official SDK proof for an operator-selected real delivery request."""

import argparse
import json
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import anyio
from mcp import Client, StdioServerParameters

from apizr.delivery_batch import BatchRequest, BatchResult


async def exercise(
    config: dict, operation: str, expected_state: str, mode: Literal["auto", "legacy"]
) -> dict:
    request_path, policy_path = Path(config["request"]), Path(config["policy"])
    raw_request, raw_policy = request_path.read_bytes(), policy_path.read_bytes()
    request = BatchRequest.model_validate_json(raw_request)
    target = StdioServerParameters(
        command=config["cli"],
        args=[
            "mcp",
            "serve",
            "--project",
            config["project"],
            "--operator-policy",
            str(policy_path),
            "--plugins-dir",
            config["store"],
            "--delivery-request",
            str(request_path),
            "--timeout-ms",
            "300000",
        ],
        cwd=Path(config["project"]).parent,
        env={
            "APIZR_TEST_SECRET": "PRIVATE_PARENT_SECRET",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    forbidden = [
        str(request_path),
        str(policy_path),
        config["store"],
        request.evidence_root,
        "PRIVATE_PARENT_SECRET",
    ]
    for destination in request.destinations:
        forbidden.extend(
            [
                destination.push.docker.socket,
                destination.push.docker.executable,
                destination.push.authentication.config_file,
            ]
        )
        if destination.proof:
            forbidden.extend(
                [
                    destination.proof.signing.key_file,
                    destination.proof.verification.trust_store,
                ]
            )
    readonly = target.model_copy(update={"args": target.args[:-4]})
    async with Client(readonly, mode=mode) as client:
        original_tools = (await client.list_tools()).tools
        assert [t.name for t in original_tools] == [
            "apizr_analyze",
            "apizr_readiness",
            "apizr_plan_exposure",
        ]
        assert all(
            t.annotations and t.annotations.read_only_hint for t in original_tools
        )
        refused = await client.call_tool("apizr_delivery_run", {})
        assert refused.is_error
    async with Client(target, mode=mode, read_timeout_seconds=330) as client:
        assert client.protocol_version == (
            "2025-11-25" if mode == "legacy" else "2026-07-28"
        )
        assert client.server_info is not None
        assert (
            client.server_info.version == version("outerspace-apizr-mcp") == "0.4.2rc2"
        )
        tools = (await client.list_tools()).tools
        assert tools[:3] == original_tools
        assert [t.name for t in tools] == [
            "apizr_analyze",
            "apizr_readiness",
            "apizr_plan_exposure",
            "apizr_delivery_status",
            "apizr_delivery_run",
            "apizr_delivery_resume",
        ]
        for tool in tools[3:]:
            effect = tool.name != "apizr_delivery_status"
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is (not effect)
            assert tool.annotations.open_world_hint is effect
            assert tool.annotations.destructive_hint is False
            assert tool.annotations.idempotent_hint is (not effect)
            assert tool.input_schema["additionalProperties"] is False
        initial = await client.call_tool("apizr_delivery_status", {})
        assert not initial.is_error and initial.structured_content is not None
        before = BatchResult.model_validate_json(json.dumps(initial.structured_content))
        if operation == "run":
            assert all(o.state == "not_started" for o in before.outcomes)
        else:
            assert before.state == "partial"
        confirmation = {
            "expected_delivery_manifest_digest": before.delivery_manifest_digest.model_dump(
                mode="json"
            )
        }
        assert before.delivery_manifest_digest == request.build.delivery_manifest_digest
        try:
            # Neither file is reopened by the server. Even invalid replacement
            # bytes cannot expand, revoke or replace this running session.
            request_path.write_text("PRIVATE_REPLACED_REQUEST")
            policy_path.write_text("PRIVATE_REPLACED_POLICY")
            reply = await client.call_tool("apizr_delivery_" + operation, confirmation)
            assert not reply.is_error and reply.structured_content is not None, reply
            delivered = BatchResult.model_validate_json(
                json.dumps(reply.structured_content)
            )
            assert delivered.state == expected_state, delivered.model_dump(mode="json")
            status = await client.call_tool("apizr_delivery_status", {})
            assert (
                not status.is_error
                and status.structured_content == reply.structured_content
            )
            repeated = await client.call_tool("apizr_delivery_run", confirmation)
            assert (
                repeated.is_error
                and repeated.structured_content["error"]["code"]
                == "delivery_evidence_invalid"
            )
            replacement = await client.call_tool(
                "apizr_delivery_resume", confirmation | {"request": str(request_path)}
            )
            assert (
                replacement.is_error
                and replacement.structured_content["error"]["code"]
                == "invalid_arguments"
            )
            for response in (initial, reply, status, repeated, replacement):
                encoded = response.model_dump_json()
                assert not any(private in encoded for private in forbidden)
                assert "PRIVATE_REPLACED" not in encoded
        finally:
            request_path.write_bytes(raw_request)
            policy_path.write_bytes(raw_policy)
    return delivered.model_dump(mode="json", by_alias=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--operation", choices=["run", "resume"], required=True)
    parser.add_argument(
        "--expected-state", choices=["partial", "complete"], required=True
    )
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    result = anyio.run(
        exercise,
        json.loads(args.config.read_text()),
        args.operation,
        args.expected_state,
        "legacy" if args.legacy else "auto",
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
