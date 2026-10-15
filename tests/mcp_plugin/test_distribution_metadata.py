"""All advertised contracts and the installation presentation remain coherent."""

import json
from copy import deepcopy
from pathlib import Path

import anyio
import pytest
from build_mcp_bundle import build
from delivery_batch.test_batch import Managed
from mcp import Client
from mcp_distribution.metadata import ROOT, validate_metadata
from mcp_registry_proof import documented_inputs
from mcp_schema_proof import discovery
from mcp_tool_metadata import review, validate_result
from test_mcp_delivery import arguments, configured
from test_server import setup

from apizr.delivery_batch import operations
from apizr.workspace.analysis_session import load_scope
from apizr.workspace.operator_policy import load_operator_policy


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("delivery", [False, True])
def test_all_advertised_results_match_live_schemas_and_unknown_arguments_refuse(
    project, tmp_path, monkeypatch, mode, delivery
):
    _, app = setup(project, monkeypatch)
    batch = None
    if delivery:
        batch, _, app = configured(project, tmp_path)
        monkeypatch.setattr(operations, "run_extension", Managed())

    async def exercise():
        async with Client(app, mode=mode) as client:
            tools = [
                t.model_dump(mode="json", by_alias=True)
                for t in (await client.list_tools()).tools
            ]
            rows = review(discovery(client, tools), delivery=delivery)
            assert len(rows) == (9 if delivery else 6)
            for tool in tools:
                args = (
                    arguments(batch)
                    if tool["name"] in {"apizr_delivery_run", "apizr_delivery_resume"}
                    else {}
                )
                refused = await client.call_tool(
                    tool["name"], {**args, "operator_policy": "UNTRUSTED"}
                )
                assert (
                    refused.is_error
                    and refused.structured_content["error"]["code"]
                    == "invalid_arguments"
                )
                result = await client.call_tool(tool["name"], args)
                if tool["name"].startswith("apizr_experiment_"):
                    # This fixture has analysis/delivery authority only: a
                    # new history tool must not inherit either permission.
                    assert result.is_error
                    assert result.structured_content["error"]["code"] in {
                        "invalid_arguments",
                        "operator_operation_denied",
                    }
                else:
                    validate_result(tool, result)

    anyio.run(exercise)


@pytest.mark.parametrize(
    "fault",
    [
        "title",
        "description",
        "nested_description",
        "output",
        "annotation",
        "unknown_fields",
    ],
)
def test_review_detects_real_public_contract_gaps(project, tmp_path, fault):
    _, _, app = configured(project, tmp_path)

    async def exercise():
        async with Client(app) as client:
            data = discovery(
                client,
                [
                    t.model_dump(mode="json", by_alias=True)
                    for t in (await client.list_tools()).tools
                ],
            )
        broken = deepcopy(data)
        tool = next(t for t in broken["tools"] if t["name"] == "apizr_delivery_run")
        if fault == "title":
            tool["title"] = None
        elif fault == "description":
            tool["description"] = "Run"
        elif fault == "nested_description":
            del tool["inputSchema"]["$defs"]["Digest"]["properties"]["value"][
                "description"
            ]
        elif fault == "output":
            tool["outputSchema"] = {}
        elif fault == "annotation":
            tool["annotations"]["readOnlyHint"] = True
        else:
            tool["inputSchema"]["additionalProperties"] = True
        with pytest.raises(AssertionError):
            review(broken, delivery=True)

    anyio.run(exercise)


def test_registry_new_user_can_create_valid_inputs_from_linked_documentation(tmp_path):
    descriptor = validate_metadata()
    values = documented_inputs(tmp_path, str(tmp_path / "explicit-store"))
    assert {a["name"] for a in descriptor["packages"][0]["packageArguments"]} == set(
        values
    )
    policy = load_operator_policy(Path(values["--operator-policy"]))
    scope = load_scope(Path(values["--project"]), policy)
    assert scope.root == str(tmp_path / "registry-new-user")
    assert len(policy.grants) == 1
    assert not Path(values["--plugins-dir"]).exists()


def test_prepared_mcpb_is_reproducible_and_only_delegates(tmp_path):
    import zipfile

    first, second = tmp_path / "first.mcpb", tmp_path / "second.mcpb"
    assert build(first) == build(second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {
            "manifest.json",
            "pyproject.toml",
            "src/server.py",
            "LICENSE",
        }
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["server"]["type"] == "uv"
        assert manifest["compatibility"]["platforms"] == ["darwin", "linux"]
        assert "--delivery-request" not in json.dumps(manifest)
        assert (
            "from apizr_mcp.launcher import main"
            in archive.read("src/server.py").decode()
        )


def test_publisher_is_manual_oidc_and_preflight_precedes_authentication():
    workflow = (ROOT / ".github/workflows/publish-mcp.yml").read_text()
    assert (
        "workflow_dispatch:" in workflow
        and "github.ref == 'refs/heads/master'" in workflow
    )
    assert "id-token: write" in workflow and "login github-oidc" in workflow
    assert (
        workflow.index("verify_mcp_publication.py")
        < workflow.index('"$RUNNER_TEMP/mcp-publisher" validate')
        < workflow.index("login github-oidc")
        < workflow.index("publish server.json")
    )
    assert "--source-sha" in workflow and "--release-tag" in workflow
    assert "GLAMA_API_KEY" not in workflow and "SMITHERY_API_KEY" not in workflow


def test_no_ordinary_workflow_queries_external_indexes():
    for file in (ROOT / ".github/workflows").iterdir():
        contents = file.read_text()
        if file.name == "verify-mcp-distribution.yml":
            assert "workflow_dispatch:" in contents
            assert not any(
                trigger in contents
                for trigger in ("  push:", "  pull_request:", "  schedule:")
            )
            assert (
                "secrets.GLAMA_API_KEY" in contents
                and "secrets.SMITHERY_API_KEY" in contents
            )
            assert (
                "verify_mcp_publication.py" in contents
                and "--require-complete" in contents
            )
            continue
        assert "verify_mcp_distribution.py" not in contents
        assert "GLAMA_API_KEY" not in contents and "SMITHERY_API_KEY" not in contents
