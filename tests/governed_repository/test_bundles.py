import hashlib
import json
from pathlib import Path

import pytest
from oci.helpers import IMAGE
from repository_interfaces.test_golden import FIXTURE as DIRECT_FIXTURE
from repository_interfaces.test_golden import render as direct_render

from apizr.execution.policy import ExecutionPolicy
from apizr.oci.model import ExecutionPolicyV2
from apizr.repository_interfaces.errors import BundleRefused
from apizr.repository_interfaces.generator import render_repository_bundle

from .helpers import inputs

ROOT = Path(__file__).parents[2]


def test_direct_baseline_exact_every_artifact():
    pinned = json.loads(
        (ROOT / "tests/fixtures/governed-repository/direct-baseline.json").read_bytes()
    )
    assert pinned["baseline"] == "5b898c66c4d501f04b1838898f1650c7744dcfea"
    for transport in ("rest", "mcp"):
        artifacts = direct_render(DIRECT_FIXTURE / "project", transport)
        assert {
            name: hashlib.sha256(content).hexdigest()
            for name, content in artifacts.items()
        } == pinned["artifacts"][transport]


@pytest.mark.parametrize("transport", ["rest", "mcp"])
@pytest.mark.parametrize("policy", [ExecutionPolicy(), ExecutionPolicyV2()])
def test_bridge_hashes_plans_public_surface_and_determinism(transport, policy):
    values = inputs(policy, transport)
    args = {
        "interface": transport,
        "execution_policy": policy,
        "runtime_image": IMAGE if isinstance(policy, ExecutionPolicyV2) else None,
    }
    artifacts = render_repository_bundle(*values, **args)
    reverse = (*values[:-1], dict(reversed(list(values[-1].items()))))
    assert artifacts == render_repository_bundle(*reverse, **args)
    bridge = json.loads(artifacts["execution/bundle.json"])
    manifest = json.loads(artifacts[f"apizr-repository-{transport}.json"])
    assert manifest["schema_version"] == f"apizr.repository-{transport}/v1"
    assert bridge["schema_version"] == (
        "apizr.repository-execution-bundle/v2"
        if policy.backend == "oci-container"
        else "apizr.repository-execution-bundle/v1"
    )
    assert len(bridge["capabilities"]) == 8
    assert set(manifest["artifacts"]) == set(artifacts) - {
        f"apizr-repository-{transport}.json"
    }
    assert set(bridge["artifacts"]) == set(manifest["artifacts"]) - {
        "execution/bundle.json"
    }
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256(artifacts[name]).hexdigest() == digest["value"]
    for identity, entry in bridge["capabilities"].items():
        assert (
            entry["path"]
            == "execution/plans/"
            + hashlib.sha256(identity.encode()).hexdigest()
            + ".json"
        )
    assert not any(
        "analyzer" in name
        or "scanner" in name
        or "inspection.py" in name
        or "builder.py" in name
        or "/legacy/" in name
        for name in artifacts
    )
    assert (
        "apizr_runtime.py" not in artifacts
        and "apizr_repository_runtime.py" not in artifacts
    )
    assert (
        b"sample.api.helper"
        not in artifacts["openapi.json" if transport == "rest" else "mcp-tools.json"]
    )


def test_backend_mismatch_and_image_requirements():
    values = inputs()
    with pytest.raises(BundleRefused, match="003"):
        render_repository_bundle(
            *values,
            interface="rest",
            execution_policy=ExecutionPolicyV2(),
            runtime_image=IMAGE,
        )
    for policy, image in [
        (ExecutionPolicyV2(), None),
        (ExecutionPolicy(), IMAGE),
        (None, IMAGE),
    ]:
        with pytest.raises(ValueError):
            render_repository_bundle(
                *values, interface="rest", execution_policy=policy, runtime_image=image
            )


def test_embedded_definitions_reuse_reviewed_logic():
    from apizr.governed.embedding import definition
    from apizr.governed_repository.embedding import runtime_files

    files = runtime_files("rest")
    for path, names in {
        "execution/supervisor.py": ["exchange", "kill_group", "worker_environment"],
        "repository_interfaces/runtime.py": ["RepositoryLoader", "read_artifact"],
        "oci/docker.py": ["DockerProvider"],
    }.items():
        for name in names:
            original = definition(path, name).replace(
                "from apizr.", "from apizr_governed."
            )
            assert original in files["apizr_governed/" + path].decode()
