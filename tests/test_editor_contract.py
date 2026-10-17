"""Cross-client conformance, actual stdio and canonical read-only evidence parity."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from analysis_authorization import analysis_policy
from jsonschema import Draft202012Validator
from jsonschema import ValidationError as SchemaError
from pydantic import ValidationError

from apizr import tracking
from apizr.editor_contracts import EditorRequest, EditorResponse, capabilities
from apizr.experiments.comparison import compare_runs
from apizr.experiments.history import list_runs
from apizr.experiments.store import DEFAULT_STORE, records
from apizr.workspace.analysis_session import load_scope
from apizr.workspace.editor_session import execute
from apizr.workspace.operator_policy import OperatorPolicy

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests/fixtures/editor-contracts/conformance.json").read_text()
)


@pytest.mark.parametrize("payload", CASES["accepted"])
def test_any_client_can_validate_accepted_requests(payload):
    Draft202012Validator(EditorRequest.model_json_schema()).validate(payload)
    assert (
        EditorRequest.model_validate_json(json.dumps(payload), strict=True).operation
        == payload["operation"]
    )


@pytest.mark.parametrize("payload", CASES["rejected"])
def test_schema_and_engine_reject_the_same_incompatible_or_unsafe_requests(payload):
    with pytest.raises(SchemaError):
        Draft202012Validator(EditorRequest.model_json_schema()).validate(payload)
    with pytest.raises(ValidationError):
        EditorRequest.model_validate_json(json.dumps(payload), strict=True)


def policy(root, *, history=True, store=".apizr/experiments/v1"):
    value = analysis_policy(root).model_dump(mode="json", by_alias=True)
    if history:
        value["grants"].append(
            {
                "adapter": "experiments",
                "operation": "history.read",
                "target": {"kind": "local", "root": str(root)},
                "store": store,
                "permissions": ["experiments.read"],
            }
        )
    return OperatorPolicy.model_validate_json(json.dumps(value), strict=True)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "apizr.toml").write_text(
        'schema_version="apizr.project/v1"\nroot="."\n'
    )
    (tmp_path / "model.py").write_text(
        "def predict(value: float) -> float:\n    return value * 2\n"
    )
    shutil.copytree(
        ROOT / "tests/fixtures/experiments/published-0.4.5", tmp_path / DEFAULT_STORE
    )
    with tracking.session(root=tmp_path, source="model.py") as capture:
        tracking.log_parameter("rate", 0.2)
        tracking.log_metric("score", 0.9)
    return tmp_path, capture.record


def request(operation, **arguments):
    return EditorRequest.model_validate(
        {"request_id": "client-1", "operation": operation, "arguments": arguments}
    )


def tree(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }


def test_discovery_is_actual_engine_metadata_and_all_operations_are_read_only(
    monkeypatch,
):
    import socket

    def denied(*args, **kwargs):
        raise AssertionError("No discovery network effects")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket, "socket", denied)
    result = capabilities()
    assert len({op.name for op in result.operations}) == 6
    assert all(op.read_only for op in result.operations)
    assert result.providers[0].identity.name == "apizr.builtin"
    response = execute(request("capabilities"))
    assert response.ok and response.value == result


def test_history_shares_engine_validation_and_never_mutates_evidence(project):
    root, sdk = project
    scope = load_scope(root / "apizr.toml", policy(root))
    before = tree(root)
    listing = execute(request("experiment_list"), scope)
    assert listing.ok and listing.value == list_runs(
        root / DEFAULT_STORE, include_values=True
    )
    assert any(r.capture.producer == "apizr.tracking" for r in listing.value.runs)
    shown = execute(request("experiment_show", run_id=sdk.run_digest[:12]), scope)
    assert shown.ok and shown.value == sdk
    cli = next(
        r for r in records(root / DEFAULT_STORE) if r.run.schema_version.endswith("/v1")
    )
    diff = execute(
        request("experiment_diff", run_a=cli.run_digest, run_b=sdk.run_digest), scope
    )
    assert diff.ok and diff.value == compare_runs(cli, sdk)
    assert tree(root) == before
    for result in (listing, shown, diff):
        assert result.request_id == "client-1"
        Draft202012Validator(EditorResponse.model_json_schema()).validate(
            result.model_dump(mode="json")
        )


def test_history_requires_its_own_exact_grant_before_store_io(project, monkeypatch):
    from apizr.workspace import editor_session

    root, _ = project
    scope = load_scope(root / "apizr.toml", policy(root, history=False))

    def refuse(*args, **kwargs):
        raise AssertionError("Unauthorized history was read")

    monkeypatch.setattr(editor_session, "list_runs", refuse)
    result = execute(request("experiment_list"), scope)
    assert not result.ok and result.diagnostics[0].code == "operator_operation_denied"
    wrong = load_scope(root / "apizr.toml", policy(root, store="different-store"))
    assert (
        execute(request("experiment_list"), wrong).diagnostics[0].code
        == "operator_history_denied"
    )


def test_missing_and_corrupt_history_return_safe_owned_diagnostics(project):
    root, sdk = project
    scope = load_scope(root / "apizr.toml", policy(root))
    assert (
        execute(request("experiment_show", run_id="f" * 64), scope).diagnostics[0].code
        == "run_not_found"
    )
    path = root / DEFAULT_STORE / "runs" / (sdk.run_digest + ".json")
    path.write_text('{"PRIVATE_PAYLOAD":"not canonical"}')
    result = execute(request("experiment_list", limit=1), scope)
    assert result.diagnostics[0].code == "history_invalid"
    assert "PRIVATE_PAYLOAD" not in result.model_dump_json()


def test_inspection_and_exposure_reuse_existing_operations(project):
    from apizr.experiments.inspection import inspect_experiment

    root, _ = project
    scope = load_scope(root / "apizr.toml", policy(root))
    result = execute(request("inspect", source="model.py"), scope)
    assert result.ok and result.value == inspect_experiment(
        root / "model.py", root=root
    )
    assert (
        execute(request("plan_exposure"), scope).diagnostics[0].code
        == "policy_required"
    )
    assert (
        execute(request("inspect", source="model.py")).diagnostics[0].code
        == "project_required"
    )


def test_plan_preserves_success_and_structured_refusal(project):
    root, _ = project
    config = root / "apizr.toml"
    config.write_text(config.read_text() + '\nreadiness_policy="readiness.json"\n')
    (root / "readiness.json").write_text('{"execution":{"modes":["direct"]}}')
    scope = load_scope(root / "apizr.toml", policy(root))
    proposal = {
        "selection": {"include": ["python:model:predict"]},
        "interfaces": ["mcp"],
        "execution": {"allowed": ["direct"]},
    }
    result = execute(request("plan_exposure", policy=proposal), scope)
    assert (
        result.ok
        and result.value.capabilities[0].capability_id == "python:model:predict"
    )
    proposal["selection"]["include"] = ["python:model:absent"]
    refused = execute(request("plan_exposure", policy=proposal), scope)
    assert not refused.ok and refused.diagnostics[0].code == "exposure_refused"
    assert refused.exposure_diagnostics[0].code == "unknown_id"


def test_inspection_retains_notebook_cell_locations_without_execution(project):
    root, _ = project
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "id": "intro", "source": "Notes"},
            {
                "cell_type": "code",
                "metadata": {},
                "id": "code",
                "execution_count": None,
                "outputs": [],
                "source": "def variadic(*items):\n    return items\n",
            },
        ],
    }
    (root / "model.ipynb").write_text(json.dumps(notebook))
    scope = load_scope(root / "apizr.toml", policy(root))
    response = execute(request("inspect", source="model.ipynb"), scope)
    assert response.ok and response.diagnostics
    assert response.diagnostics[0].location.cell_index == 1
    assert response.diagnostics[0].location.code_cell_index == 0
    assert response.diagnostics[0].location.cell_line >= 1


@pytest.mark.parametrize(
    "case,code",
    [
        ("none", "operator_policy_required"),
        ("analysis", "operator_operation_denied"),
        ("empty-permissions", "operator_permissions_denied"),
        ("other-root", "operator_history_denied"),
        ("invalid-store", "operator_source_invalid"),
        ("valid", "authorized"),
    ],
)
def test_history_decision_is_exact_and_pure(project, case, code):
    from apizr.contracts.analysis import LocalTarget
    from apizr.workspace.operator_policy import decide_history

    root, _ = project
    authority = policy(root, history=case != "analysis")
    if case == "none":
        authority = None
    elif case in {"empty-permissions", "other-root"}:
        data = authority.model_dump(mode="json", by_alias=True)
        if case == "empty-permissions":
            data["grants"][-1]["permissions"] = []
        else:
            data["grants"][-1]["target"]["root"] += "-other"
        authority = OperatorPolicy.model_validate_json(json.dumps(data))
    result = decide_history(
        authority,
        LocalTarget(root=str(root)),
        "../outside" if case == "invalid-store" else DEFAULT_STORE.as_posix(),
    )
    assert result.code == code and result.allowed is (case == "valid")


def test_history_reads_do_not_import_the_producing_provider(project):
    root, sdk = project
    authority = root / "operator.json"
    authority.write_text(policy(root).model_dump_json(by_alias=True))
    program = """
import importlib.abc,sys
class NoProvider(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('apizr.scientific_providers.builtin'):
            raise ImportError('producing provider unavailable')
sys.meta_path.insert(0,NoProvider())
from apizr.cli import main
raise SystemExit(main(['editor','--project',sys.argv[1],'--operator-policy',sys.argv[2]]))
"""
    payload = (
        request("experiment_show", run_id=sdk.run_digest).model_dump_json().encode()
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", program, str(root / "apizr.toml"), str(authority)],
        input=payload,
        capture_output=True,
        timeout=30,
    )
    assert run.returncode == 0 and not run.stderr
    assert EditorResponse.model_validate_json(run.stdout).value == sdk


def test_exported_editor_schemas_match_the_canonical_models():
    from apizr.editor_contracts.model import EngineCapabilities

    for name, model in (
        ("request", EditorRequest),
        ("response", EditorResponse),
        ("capabilities", EngineCapabilities),
    ):
        schema = json.loads(
            (ROOT / f"docs/specs/apizr-editor-{name}-v1.schema.json").read_text()
        )
        assert schema == model.model_json_schema()


@pytest.mark.parametrize(
    "source,depth",
    [
        ("src/ignored/private.py", 64),
        ("other/private.py", 64),
        ("src/deep/deeper/private.py", 1),
    ],
)
def test_editor_cannot_enlarge_the_captured_source_scope(
    project, monkeypatch, source, depth
):
    from apizr.experiments import inspection
    from apizr.repository import ScanPolicy

    root, _ = project
    scope = load_scope(root / "apizr.toml", policy(root))
    scope = scope.model_copy(
        update={
            "scan": ScanPolicy(
                source_roots=("src",),
                excluded_directories=("ignored",),
                max_depth=depth,
            )
        }
    )

    def refused(*args, **kwargs):
        raise AssertionError("Out-of-scope source was inspected")

    monkeypatch.setattr(inspection, "inspect_experiment", refused)
    result = execute(request("inspect", source=source), scope)
    assert not result.ok and result.diagnostics[0].code == "source_outside_scope"


def test_editor_honors_the_project_byte_limit_before_inspection(project):
    from apizr.repository import ScanPolicy

    root, _ = project
    scope = load_scope(root / "apizr.toml", policy(root))
    scope = scope.model_copy(update={"scan": ScanPolicy(max_file_bytes=16)})
    response = execute(request("inspect", source="model.py"), scope)
    assert not response.ok and response.diagnostics[0].code == "operation_failed"


@pytest.mark.parametrize(
    "scenario",
    CASES["responses"],
    ids=[item["scenario"] for item in CASES["responses"]],
)
def test_frozen_response_fixtures_are_reusable_by_any_client(tmp_path, scenario):
    scope = None
    if scenario["scenario"] == "authorized-empty-history":
        (tmp_path / "apizr.toml").write_text(
            'schema_version="apizr.project/v1"\nroot="."\n'
        )
        scope = load_scope(tmp_path / "apizr.toml", policy(tmp_path))
    parsed = EditorRequest.model_validate_json(json.dumps(scenario["request"]))
    before = tree(tmp_path)
    actual = execute(parsed, scope).model_dump(mode="json")
    assert actual == scenario["expected"]
    Draft202012Validator(EditorResponse.model_json_schema()).validate(
        scenario["expected"]
    )
    assert before == tree(tmp_path)


def call_cli(data, *args):
    return subprocess.run(
        [sys.executable, "-m", "apizr.cli", "editor", *map(str, args)],
        input=json.dumps(data).encode() if not isinstance(data, bytes) else data,
        capture_output=True,
        timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_real_stdio_is_one_closed_response_and_cli_history_matches(project):
    root, sdk = project
    authority = root / "operator.json"
    authority.write_text(policy(root).model_dump_json(by_alias=True))
    args = ("--project", root / "apizr.toml", "--operator-policy", authority)
    result = call_cli(
        request("experiment_show", run_id=sdk.run_digest).model_dump(mode="json"), *args
    )
    assert result.returncode == 0 and not result.stderr
    assert EditorResponse.model_validate_json(result.stdout).value == sdk
    assert len(result.stdout.splitlines()) == 1
    cli = subprocess.run(
        [
            sys.executable,
            "-m",
            "apizr.cli",
            "experiment",
            "show",
            sdk.run_digest,
            "--store",
            str(root / DEFAULT_STORE),
            "--format",
            "json",
        ],
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["value"] == json.loads(cli.stdout)


@pytest.mark.parametrize(
    "data,code",
    [
        (b"{}", "invalid_request"),
        (b'{"operation":"capabilities","operation":"inspect"}', "invalid_request"),
        (b"x" * 65537, "request_too_large"),
        ({"operation": "capabilities", "schema_version": "unknown"}, "invalid_request"),
    ],
)
def test_real_stdio_refuses_invalid_inputs_without_tracebacks(data, code):
    result = call_cli(data)
    assert result.returncode == 2 and not result.stderr
    response = EditorResponse.model_validate_json(result.stdout)
    assert not response.ok and response.diagnostics[0].code == code
