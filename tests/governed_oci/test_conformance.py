import json
import sys

import anyio
import pytest
from fastapi.testclient import TestClient
from governed.helpers import SOURCE
from governed.test_conformance import CORPUS
from mcp import Client

from apizr.execute_cli import main as execute_cli
from apizr.execution import ExecutionPolicy
from apizr.generators.mcp import generate as mcp_generate
from apizr.generators.mcp.runtime import create_server as direct_mcp
from apizr.generators.rest import generate as rest_generate
from apizr.generators.rest.runtime import create_app as direct_rest
from apizr.governed.mcp import create_server as local_mcp
from apizr.governed.rest import create_app as local_rest
from apizr.governed_oci.mcp import create_server as oci_mcp
from apizr.governed_oci.rest import create_app as oci_rest
from apizr.inspection import inspect_source
from apizr.oci.model import ExecutionPolicyV2

pytestmark = pytest.mark.timeout(180)


def test_shared_eight_entrypoint_corpus_and_state(worker_image, tmp_path, capsys):
    for mode in ["direct", "local", "oci"]:
        for transport, generate in [("rest", rest_generate), ("mcp", mcp_generate)]:
            root = tmp_path / (mode + "-" + transport)
            generate(
                inspect_source(SOURCE, module_name="conformance"),
                SOURCE,
                root,
                execution_policy=None
                if mode == "direct"
                else ExecutionPolicy()
                if mode == "local"
                else ExecutionPolicyV2(),
                runtime_image=worker_image if mode == "oci" else None,
            )
            document = json.loads((root / f"apizr-{transport}.json").read_bytes())
            try:
                if transport == "rest":
                    app = (
                        direct_rest(
                            root, {**document, "endpoints": document["capabilities"]}
                        )
                        if mode == "direct"
                        else local_rest(root)
                        if mode == "local"
                        else oci_rest(root)
                    )
                    with TestClient(app) as client:
                        for name, args, valid, value in CORPUS:
                            response = client.post("/capabilities/" + name, json=args)
                            assert response.status_code == (200 if valid else 422)
                            if valid:
                                assert response.json() == value
                        assert client.post("/capabilities/counter", json={}).json() == [
                            1,
                            1,
                        ]
                        assert client.post("/capabilities/counter", json={}).json() == (
                            [2, 2] if mode == "direct" else [1, 1]
                        )
                else:

                    async def check(root=root, document=document, mode=mode):
                        server = (
                            direct_mcp(root, document)
                            if mode == "direct"
                            else local_mcp(root)
                            if mode == "local"
                            else oci_mcp(root)
                        )
                        async with Client(server) as client:
                            for name, args, valid, value in CORPUS:
                                response = await client.call_tool(name, args)
                                assert response.is_error != valid
                                if valid:
                                    assert response.structured_content == value
                            assert (
                                await client.call_tool("counter", {})
                            ).structured_content == [1, 1]
                            assert (
                                await client.call_tool("counter", {})
                            ).structured_content == (
                                [2, 2] if mode == "direct" else [1, 1]
                            )

                    anyio.run(check)
            finally:
                sys.modules.pop("conformance", None)
    source = tmp_path / "source.py"
    source.write_bytes(SOURCE)
    arguments = tmp_path / "args.json"
    policy = tmp_path / "policy.json"
    for mode in ["local", "oci"]:
        policy.write_text(
            "{}" if mode == "local" else '{"schema_version":"apizr.execution/v2"}'
        )
        for name, args, valid, value in CORPUS:
            arguments.write_text(json.dumps(args))
            command = [
                str(source),
                name,
                "--arguments",
                str(arguments),
                "--policy",
                str(policy),
            ]
            if mode == "oci":
                command += [
                    "--runtime-image",
                    worker_image.image,
                    "--runtime-platform",
                    worker_image.platform,
                ]
            assert execute_cli(command) == (0 if valid else 1)
            result = json.loads(capsys.readouterr().out)
            assert result["status"] == ("success" if valid else "invalid_input")
            if valid:
                assert result["value"] == value
