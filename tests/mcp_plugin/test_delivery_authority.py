"""MCP transport cannot widen existing managed plugin identity/operation grants."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import anyio
import pytest
from apizr_mcp import server
from apizr_mcp.model import ServerLimits
from batch_inputs import request
from delivery_batch.test_batch import Managed
from mcp import Client

from apizr.delivery_batch import BatchResult, operations
from apizr.local_plugins import PluginError, activation
from apizr.local_plugins.models import Installation
from apizr.mcp_session import DeliverySession, McpSession
from apizr.operator_policy import OperatorPolicy, PluginIdentity


@pytest.mark.parametrize(
    "fault",
    [
        "repository",
        "attest",
        "publish",
        "admit",
        "observe",
        "partial_grants",
        "version",
        "closure",
        "inactive",
    ],
)
def test_exact_existing_grants_remain_authoritative(
    project, tmp_path, monkeypatch, fault
):
    batch = request(tmp_path)
    managed = Managed()
    records = {}
    for name, module in [
        (operations.OCI, "apizr_oci.protocol"),
        (operations.ATTEST, "apizr_attest.protocol"),
    ]:
        records[name] = Installation.model_validate_json(
            json.dumps(
                {
                    "schema": "apizr.extension-manifest/v1",
                    "name": name,
                    "version": "0.4.2",
                    "module": module,
                    "protocol": "apizr.extension/v1",
                    "sha256": "a" * 64,
                    "environment_id": "b" * 32,
                    "python": "/PRIVATE/python",
                    "lock_sha256": "c" * 64,
                    "dependencies": [],
                }
            )
        )
    grants = [g.model_dump(mode="json") for g in project[1].operator_policy.grants]
    for index, destination in enumerate(batch.destinations):
        for operation in ("push", "observe", "attest", "publish", "admit"):
            if index == 1 and (
                (fault == "repository" and operation == "push") or fault == operation
            ):
                continue
            plugin = (
                operations.OCI
                if operation in {"push", "observe"}
                else operations.ATTEST
            )
            grant = {
                "plugin": PluginIdentity.from_installation(records[plugin]).model_dump(
                    mode="json"
                ),
                "operation": operation,
                "repository": destination.push.destination.rsplit(":", 1)[0],
                "permissions": ["registry.read"]
                if operation == "observe"
                else ["registry.read", "registry.publish"],
            }
            if operation == "attest":
                grant.update(destination.proof.signing.model_dump())
                grant.update(
                    expected_signer=destination.proof.verification.expected_signer,
                    permissions=["registry.read", "receipt.sign", "timestamp.request"],
                )
            if index == 1 and fault == "partial_grants" and operation == "push":
                grants.extend(
                    [
                        {**grant, "permissions": ["registry.read"]},
                        {**grant, "permissions": ["registry.publish"]},
                    ]
                )
            else:
                grants.append(grant)
    authority = OperatorPolicy.model_validate_json(
        json.dumps({"schema": "apizr.operator-policy/v1", "grants": grants})
    )
    captured = project[1].model_copy(update={"operator_policy": authority})
    session = McpSession(
        analysis=captured,
        delivery=DeliverySession(request=batch, plugins_dir=str(tmp_path / "plugins")),
    )
    calcs = server.Calculations(session, ServerLimits())

    @contextmanager
    def admitted(name, **kwargs):
        assert kwargs["directory"] == Path(session.delivery.plugins_dir)
        if fault == "inactive":
            raise PluginError("plugin_inactive")
        record = records[name]
        if fault == "version":
            record = record.model_copy(update={"version": "0.4.2rc3"})
        if fault == "closure":
            record = record.model_copy(update={"lock_sha256": "d" * 64})
        yield record, 0

    def invoke(python, module, operation, data, **kwargs):
        plugin = operations.OCI if module == "apizr_oci.protocol" else operations.ATTEST
        assert kwargs["environment"] == {}
        return managed(plugin, operation, data, **kwargs)

    monkeypatch.setattr(activation, "admitted_extension", admitted)
    monkeypatch.setattr(activation, "invoke_extension", invoke)
    monkeypatch.setattr(operations, "run_extension", activation.run_extension)

    def compiler_worker(python, module, operation, data, **kwargs):
        worker_policy = data["scope"]["operator_policy"]
        assert len(worker_policy["grants"]) == 1
        assert worker_policy["grants"][0]["operation"] == "analyze"
        encoded = json.dumps(data)
        for forbidden in (
            "key_file",
            "plugins_dir",
            "evidence_root",
            "PRIVATE",
            "destinations",
        ):
            assert forbidden not in encoded
        assert kwargs["environment"] == {}
        return SimpleNamespace(
            result={"ok": False, "error": {"code": "fixture", "diagnostics": []}}
        )

    monkeypatch.setattr(server, "invoke_extension", compiler_worker)

    async def exercise():
        async with Client(server.create_server(calcs)) as client:
            analyzed = await client.call_tool("apizr_analyze", {})
            assert analyzed.structured_content["error"]["code"] == "fixture"
            args = {
                "expected_delivery_manifest_digest": batch.build.delivery_manifest_digest.model_dump(
                    mode="json"
                )
            }
            response = await client.call_tool("apizr_delivery_run", args)
            assert not response.is_error
            if fault == "observe":
                assert response.structured_content["state"] == "complete"
                managed.calls.clear()
                response = await client.call_tool("apizr_delivery_resume", args)
                assert not response.is_error
            result = BatchResult.model_validate_json(
                json.dumps(response.structured_content)
            )
            assert result.state == (
                "failed" if fault in {"version", "closure", "inactive"} else "partial"
            )
            assert result.outcomes[1].diagnostic == (
                "transfer_failed" if fault == "inactive" else "authorization_refused"
            )
            refused = "push" if fault in {"repository", "partial_grants"} else fault
            assert not any(
                op == refused and repo.endswith("service-1")
                for op, repo, _ in managed.calls
            )
            if fault in {"version", "closure", "inactive"}:
                assert managed.calls == []
            assert "PRIVATE" not in response.model_dump_json()

    anyio.run(exercise)
