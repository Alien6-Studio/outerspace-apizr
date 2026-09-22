import json

import pytest
from oci.helpers import IMAGE

from apizr.capabilities.model import Digest
from apizr.execution.policy import PolicyRefused
from apizr.governed_repository.runtime import GovernedRuntime
from apizr.interfaces.serialization import json_bytes
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_execution.docker import RepositoryDockerProvider

from .helpers import bundle


def rehash(root, bridge, manifest):
    def digest(path):
        return Digest.of_bytes((root / path).read_bytes()).model_dump(mode="json")

    bridge["artifacts"] = {path: digest(path) for path in bridge["artifacts"]}
    (root / "execution/bundle.json").write_bytes(json_bytes(bridge))
    manifest["artifacts"] = {
        path: digest(path) for path in [*bridge["artifacts"], "execution/bundle.json"]
    }
    (root / "apizr-repository-rest.json").write_bytes(json_bytes(manifest))


@pytest.mark.parametrize(
    "mutation",
    [
        "bridge",
        "closure",
        "interface",
        "upstream",
        "exposure-policy",
        "policy",
        "contract",
        "surface",
        "invocation",
        "plan",
        "image",
    ],
)
def test_coherently_rehashed_but_inconsistent_evidence_refused(
    tmp_path, monkeypatch, mutation
):
    container = mutation == "image"
    monkeypatch.setattr(RepositoryDockerProvider, "probe", lambda *a: None)
    root = bundle(
        tmp_path / "bundle",
        policy=ExecutionPolicyV2() if container else None,
        image=IMAGE if container else None,
    )
    bridge = json.loads((root / "execution/bundle.json").read_bytes())
    manifest = json.loads((root / "apizr-repository-rest.json").read_bytes())
    wrong = Digest.of_bytes(b"wrong").model_dump(mode="json")
    if mutation == "bridge":
        bridge["transport"] = "mcp"
    elif mutation == "closure":
        bridge["artifacts"].pop("execution/worker.py")
    elif mutation == "interface":
        manifest["repository_interface_digest"] = wrong
    elif mutation == "upstream":
        (root / "capability-catalog.json").write_bytes(b"{}")
    elif mutation == "exposure-policy":
        (root / "exposure-policy.json").write_bytes(b"{}")
    elif mutation == "policy":
        bridge["policy_digest"] = wrong
    elif mutation == "contract":
        bridge["contract_digest"] = wrong
    elif mutation == "surface":
        bridge["capabilities"].pop(next(iter(bridge["capabilities"])))
    elif mutation == "invocation":
        manifest["endpoints"][0]["symbol"] = "changed"
        bridge["contract_digest"] = Digest.of_bytes(
            json_bytes(manifest["endpoints"])
        ).model_dump(mode="json")
    elif mutation == "plan":
        bridge["capabilities"][next(iter(bridge["capabilities"]))]["digest"] = wrong
    else:
        bridge["runtime"]["image"] = "sha256:" + "1" * 64
    rehash(root, bridge, manifest)
    with pytest.raises(RuntimeError, match="bundle or backend unavailable"):
        GovernedRuntime(root, "rest")


def test_bridge_inventory_mismatch_and_invocation_refusal(tmp_path, monkeypatch):
    root = bundle(tmp_path / "bundle")
    runtime = GovernedRuntime(root, "rest")

    def refuse():
        raise PolicyRefused("unsupported_control")

    monkeypatch.setattr(runtime, "validate", refuse)
    assert runtime.invoke("python:sample.api:run", {}).status == "policy_refused"
    bridge = json.loads((root / "execution/bundle.json").read_bytes())
    manifest = json.loads((root / "apizr-repository-rest.json").read_bytes())
    bridge["artifacts"].pop("requirements.txt")
    (root / "execution/bundle.json").write_bytes(json_bytes(bridge))
    manifest["artifacts"]["execution/bundle.json"] = Digest.of_bytes(
        (root / "execution/bundle.json").read_bytes()
    ).model_dump(mode="json")
    (root / "apizr-repository-rest.json").write_bytes(json_bytes(manifest))
    with pytest.raises(RuntimeError):
        GovernedRuntime(root, "rest")


def test_mcp_transport_entrypoints(tmp_path, monkeypatch):
    import sys
    from contextlib import asynccontextmanager

    from apizr.governed_repository import mcp

    root = bundle(tmp_path / "bundle", "mcp")
    calls = []

    class Server:
        def create_initialization_options(self):
            return "options"

        async def run(self, *args):
            calls.append(args)

        def streamable_http_app(self, **kwargs):
            return "app"

    @asynccontextmanager
    async def stdio():
        yield ("read", "write")

    monkeypatch.setattr(mcp, "create_server", lambda root: Server())
    monkeypatch.setattr(mcp, "stdio_server", stdio)
    monkeypatch.setattr(sys, "argv", ["server"])
    mcp.main(root)
    assert calls == [("read", "write", "options")]
    monkeypatch.setattr(
        sys, "argv", ["server", "--transport", "streamable-http", "--port", "8765"]
    )
    monkeypatch.setattr(mcp.uvicorn, "run", lambda *a, **kw: calls.append((a, kw)))
    mcp.main(root)
    assert calls[-1] == (("app",), {"host": "127.0.0.1", "port": 8765})
