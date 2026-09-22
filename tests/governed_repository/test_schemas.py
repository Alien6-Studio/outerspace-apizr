import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from oci.helpers import IMAGE

from apizr.execution.policy import ExecutionPolicy
from apizr.governed_repository.model import ContainerBundle, ExecutionBundle
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_execution.model import (
    RepositoryContainerPlan,
    RepositoryRuntimePlan,
)
from apizr.repository_interfaces.generator import render_repository_bundle

from .helpers import inputs

ROOT = Path(__file__).parents[2]
MODELS = {
    "apizr-repository-runtime-v1": RepositoryRuntimePlan,
    "apizr-repository-runtime-v2": RepositoryContainerPlan,
    "apizr-repository-execution-bundle-v1": ExecutionBundle,
    "apizr-repository-execution-bundle-v2": ContainerBundle,
}


@pytest.mark.parametrize("name,model", MODELS.items())
def test_committed_schema_matches_model(name, model):
    actual = json.loads((ROOT / "docs/specs" / f"{name}.schema.json").read_bytes())
    assert actual == model.model_json_schema()
    Draft202012Validator.check_schema(actual)


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("oci", [False, True])
def test_governed_goldens_and_schema_validation(transport, oci):
    policy = ExecutionPolicyV2() if oci else ExecutionPolicy()
    files = render_repository_bundle(
        *inputs(policy, transport),
        interface=transport,
        execution_policy=policy,
        runtime_image=IMAGE if oci else None,
    )
    name = ("oci-" if oci else "local-") + transport + ".json"
    manifest = json.loads(files[f"apizr-repository-{transport}.json"])
    bridge = json.loads(files["execution/bundle.json"])
    assert {"manifest": manifest, "bridge": bridge} == json.loads(
        (ROOT / "tests/fixtures/governed-repository" / name).read_bytes()
    )
    Draft202012Validator(
        (ContainerBundle if oci else ExecutionBundle).model_json_schema()
    ).validate(bridge)
    for item in bridge["capabilities"].values():
        Draft202012Validator(
            (
                RepositoryContainerPlan if oci else RepositoryRuntimePlan
            ).model_json_schema()
        ).validate(json.loads(files[item["path"]]))
