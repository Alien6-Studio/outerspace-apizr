"""Discovery metadata is additive; strict validation and canonical evidence stay fixed."""

import json
from pathlib import Path

import anyio
import pytest
from apizr_mcp.model import Job, PlanArguments, ViewArguments
from apizr_mcp.scope import load_scope
from apizr_mcp.server import TOOLS
from apizr_mcp.worker import calculate
from mcp import Client
from mcp_schema_proof import fingerprint, fixture, verify_schemas, without_documentation
from pydantic import ValidationError
from test_server import setup

from apizr.capabilities.model import Digest
from apizr.workspace.operator_policy import load_operator_policy


def tools_from_models():
    return [
        {
            "name": name,
            "inputSchema": inputs.model_json_schema(),
            "outputSchema": outputs.model_json_schema(),
        }
        for name, _, _, inputs, outputs in TOOLS
    ]


def test_canonical_models_document_schemas_and_validate_examples():
    tools = tools_from_models()
    verify_schemas(tools)
    for tool, (_, _, _, model, _) in zip(tools, TOOLS, strict=True):
        for example in tool["inputSchema"]["examples"]:
            model.model_validate_json(json.dumps(example), strict=True)


def test_actual_discovery_preserves_canonical_schema_metadata(project, monkeypatch):
    _, app = setup(project, monkeypatch)

    async def exercise():
        async with Client(app) as client:
            tools = [
                tool.model_dump(mode="json", by_alias=True)
                for tool in (await client.list_tools()).tools
            ]
            verify_schemas(tools)
            assert [
                {key: tool[key] for key in ("name", "inputSchema", "outputSchema")}
                for tool in tools
            ] == tools_from_models()

    anyio.run(exercise)


@pytest.mark.parametrize("model", [ViewArguments, PlanArguments])
@pytest.mark.parametrize("value", [None, "a" * 64, "0123456789abcdef" * 4])
def test_digest_accepted_values_and_omission(model, value):
    assert (
        model.model_validate_json("{}", strict=True).expected_repository_digest is None
    )
    result = model.model_validate_json(
        json.dumps({"expected_repository_digest": value}), strict=True
    )
    assert result.expected_repository_digest == value


@pytest.mark.parametrize("model", [ViewArguments, PlanArguments])
@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 63,
        "a" * 65,
        "A" * 64,
        "g" * 64,
        "sha256:" + "a" * 64,
        123,
        True,
        [],
        {"algorithm": "sha256", "value": "a" * 64},
    ],
)
def test_digest_refuses_old_invalid_values(model, value):
    with pytest.raises(ValidationError):
        model.model_validate_json(
            json.dumps({"expected_repository_digest": value}), strict=True
        )


@pytest.mark.parametrize("model", [ViewArguments, PlanArguments])
@pytest.mark.parametrize(
    "value", [{"root": "."}, {"permissions": []}, {"unknown": None}]
)
def test_unknown_fields_stay_forbidden(model, value):
    with pytest.raises(ValidationError):
        model.model_validate_json(json.dumps(value), strict=True)


@pytest.mark.parametrize(
    "value",
    [
        None,
        {
            "selection": {"include": ["python:model:predict"]},
            "interfaces": ["mcp"],
            "execution": {"allowed": ["direct"]},
        },
    ],
)
def test_policy_null_or_explicit(value):
    result = PlanArguments.model_validate_json(
        json.dumps({"policy": value}), strict=True
    )
    assert (result.policy is None) == (value is None)


@pytest.mark.parametrize(
    "section,update",
    [
        ("selection", {"include": ["predict"]}),
        ("selection", {"all": True}),
        ("eligibility", {"allow_conditional": "yes"}),
        ("eligibility", {"unknown": True}),
        ("execution", {"allowed": []}),
        ("execution", {"allowed": ["direct"], "fallback": True}),
    ],
)
def test_nested_policy_stays_strict(section, update):
    policy = {
        "interfaces": ["mcp"],
        "execution": {"allowed": ["direct"]},
        section: update,
    }
    with pytest.raises(ValidationError):
        PlanArguments.model_validate_json(json.dumps({"policy": policy}), strict=True)


def test_digest_bytes_and_all_discovery_validation_keywords_match_baseline():
    assert Digest.of_bytes(b"abc").model_dump_json() == (
        '{"algorithm":"sha256","value":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}'
    )
    baseline = json.loads(
        (Path(__file__).with_name("schema_baseline.json")).read_text()
    )
    assert (
        fingerprint(
            without_documentation(
                [
                    t
                    for t in tools_from_models()
                    if not t["name"].startswith("apizr_experiment_")
                ]
            )
        )
        == baseline["validation_schema_sha256"]
    )
    assert (
        fingerprint(
            without_documentation(
                [
                    t
                    for t in tools_from_models()
                    if t["name"].startswith("apizr_experiment_")
                ]
            )
        )
        == baseline["history_validation_schema_sha256"]
    )


@pytest.mark.parametrize("arguments", [{}, {"policy": None}])
def test_policy_fallback_and_missing_policy_are_unchanged(project, arguments):
    scope = project[1]
    parsed = PlanArguments.model_validate_json(json.dumps(arguments), strict=True)
    default = calculate(Job(scope=scope, operation="plan", arguments=parsed))
    explicit = calculate(
        Job(
            scope=scope,
            operation="plan",
            arguments=PlanArguments(policy=scope.exposure),
        )
    )
    assert default == explicit and default["ok"]
    missing = calculate(
        Job(
            scope=scope.model_copy(update={"exposure": None}),
            operation="plan",
            arguments=parsed,
        )
    )
    assert missing["error"]["code"] == "policy_required"


def test_business_results_and_canonical_evidence_match_installed_before_baseline(
    tmp_path,
):
    project, authority = fixture(tmp_path / "project")
    scope = load_scope(project, load_operator_policy(authority))
    baseline = json.loads(Path(__file__).with_name("schema_baseline.json").read_text())
    analysis = calculate(
        Job(scope=scope, operation="analyze", arguments=ViewArguments())
    )["value"]
    digest = analysis["repository_digest"]["value"]
    assert digest == baseline["repository_digest"]
    policy = {
        "selection": {"include": ["python:model:predict"]},
        "interfaces": ["mcp"],
        "execution": {"allowed": ["direct"]},
    }
    cases = {
        "analysis": ("analyze", {}),
        "pinned-readiness": ("readiness", {"expected_repository_digest": digest}),
        "summary": ("analyze", {"view": "summary"}),
        "detail": (
            "readiness",
            {"view": "detail", "capability_id": "python:model:predict", "limit": 1},
        ),
        "explicit-plan": (
            "plan",
            {"policy": policy, "expected_repository_digest": digest},
        ),
    }
    for key, (operation, arguments) in cases.items():
        model = PlanArguments if operation == "plan" else ViewArguments
        result = calculate(
            Job(
                scope=scope,
                operation=operation,
                arguments=model.model_validate_json(json.dumps(arguments), strict=True),
            )
        )
        assert result["ok"]
        assert fingerprint(result["value"]) == baseline["business_results_sha256"][key]
    assert "UNTRUSTED_SCHEMA_SENTINEL" in json.dumps(analysis)
    assert "UNTRUSTED_SCHEMA_SENTINEL" not in json.dumps(tools_from_models())
