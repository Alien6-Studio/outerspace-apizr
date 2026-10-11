"""Additive input evidence semantics preserve existing v1 canonical bytes."""

from hashlib import sha256
from pathlib import Path

import pytest
from pydantic import ValidationError

from apizr.experiments import (
    EnvironmentEvidence,
    ExperimentPlan,
    ExperimentRun,
    InputArtifact,
    InputDeclaration,
    plan_bytes,
    run_bytes,
)
from apizr.experiments import (
    EvidenceOrigin as O,
)


@pytest.mark.parametrize(
    "updates",
    [
        {"reference": "data.csv", "uri": "s3://bucket/data.csv"},
        {"content_origin": O.STATIC},
        {"content_origin": O.UNKNOWN, "digest": "a" * 64},
        {"content_origin": O.UNKNOWN, "size": 1},
        {"format_hint": "arbitrary"},
        {"unexpected": "field"},
    ],
)
def test_input_invalid_refinements(updates):
    with pytest.raises(ValidationError):
        InputArtifact(name="training", origin=O.DECLARED, **updates)


@pytest.mark.parametrize(
    "uri",
    [
        "https://user@host/data",
        "https://user:password@host/data",
        "file:///etc/passwd",
        "http://host/data",
        "s3://bucket/data?token=x",
        "s3://bucket/data#token",
        "s3://bucket/a%20b",
        "s3://bucket/..",
        "s3://bucket/./x",
        "s3://bucket//x",
        "s3://bucket/",
        "s3://bucket/x\x00",
        "https://host:443/data",
        "https://höst/x",
        "HTTPS://host/data",
        "s3://bucket/a\\b",
        "s3://bucket/" + "a" * 1024,
    ],
)
def test_restricted_uri(uri):
    with pytest.raises(ValidationError):
        InputArtifact(name="remote", uri=uri, origin=O.STATIC)


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.org/data.csv",
        "s3://my-bucket/data/train.parquet",
        "gs://bucket/a_1.npy",
        "https://host",
    ],
)
def test_reviewed_remote_syntax(uri):
    assert InputDeclaration(name="remote", uri=uri).uri == uri


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"reference": "a", "uri": "s3://bucket/a"},
        {"reference": "a", "digest": "a" * 64},
    ],
)
def test_declaration_is_only_one_selection(fields):
    with pytest.raises(ValidationError):
        InputDeclaration(name="training", **fields)


@pytest.mark.parametrize("in_environment", [False, True])
def test_plan_cannot_hide_runtime_content_under_declared_origin(pair, in_environment):
    artifact = InputArtifact(
        name="training", origin=O.DECLARED, content_origin=O.RUNTIME, digest="a" * 64
    )
    fields = (
        {"environment": EnvironmentEvidence(artifacts=(artifact,))}
        if in_environment
        else {"inputs": (artifact,)}
    )
    with pytest.raises(ValidationError, match="runtime_observation"):
        ExperimentPlan.model_validate(pair[0].model_copy(update=fields))


@pytest.mark.parametrize("in_environment", [False, True])
def test_run_requires_observed_content(pair, in_environment):
    artifact = InputArtifact(
        name="training", origin=O.RUNTIME, content_origin=O.STATIC, digest="a" * 64
    )
    fields = (
        {"environment": EnvironmentEvidence(artifacts=(artifact,))}
        if in_environment
        else {"observed_inputs": (artifact,)}
    )
    with pytest.raises(ValidationError, match="unobserved_evidence"):
        ExperimentRun.model_validate(pair[1].model_copy(update=fields))
    observed = artifact.model_copy(update={"content_origin": O.RUNTIME})
    run = ExperimentRun.model_validate(
        pair[1].model_copy(update={"observed_inputs": (observed,)})
    )
    assert run.observed_inputs[0].content_origin is O.RUNTIME


@pytest.mark.parametrize(
    "name,model,serialize,expected",
    [
        (
            "plan",
            ExperimentPlan,
            plan_bytes,
            "39be47ccee2e8afe7cfc9d8d83e09b19dbe10b9d7ae4566d85493fc1a1161f5c",
        ),
        (
            "run",
            ExperimentRun,
            run_bytes,
            "3720f1e775d41fc8c7b4176eed1bd0ab61823a12de4db24af8de16320cca472c",
        ),
    ],
)
def test_260_exact_canonical_bytes_unchanged(name, model, serialize, expected):
    raw = (
        Path(__file__).parents[1] / f"fixtures/experiments/v1/{name}.json"
    ).read_bytes()
    assert sha256(raw).hexdigest() == expected
    assert serialize(model.model_validate_json(raw)) == raw


def test_documented_input_example_runs():
    page = (Path(__file__).parents[2] / "docs/guides/experiment-inputs.md").read_text()
    code = (
        page.split("<!-- executable-input-example -->", 1)[1]
        .split("```python\n", 1)[1]
        .split("```", 1)[0]
    )
    namespace = {}
    exec(compile(code, "experiment-inputs.md", "exec"), namespace)
    assert len(namespace["identity"]) == 64
