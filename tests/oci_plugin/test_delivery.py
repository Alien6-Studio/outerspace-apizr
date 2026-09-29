"""Acyclic portable plans and substitutions at the existing build boundary."""

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest
from apizr_oci.build import build
from apizr_oci.delivery import delivery_plan
from apizr_oci.model import BuildError, BuildResult
from pydantic import ValidationError
from test_application import EXAMPLE, prepare

from apizr.application import ApplicationConfig
from apizr.capabilities.model import Digest
from apizr.compiler import render_bundle
from apizr.delivery import (
    DeliveryManifest,
    DeliveryPlan,
    GitSource,
    LocalSource,
    identity,
)
from apizr.distribution_identity import LockedDistribution
from apizr.publication_contracts import PushRequest
from apizr.repository.serialization import canonical_bytes
from apizr.repository_interfaces.output import write_bundle

from . import test_build

build_inputs = test_build.build_inputs


@pytest.fixture
def portable(tmp_path, build_inputs):
    root = tmp_path / "application"
    shutil.copytree(EXAMPLE, root)
    bundle = tmp_path / "portable"
    write_bundle(bundle, render_bundle(prepare(root), interface="rest"))
    request = build_inputs.model_copy(update={"bundle": str(bundle)})
    closure = (LockedDistribution(name="six", version="1.17.0", sha256="a" * 64),)
    return root, bundle, request, closure


def test_plan_is_portable_and_retains_each_existing_identity(portable, tmp_path):
    root, bundle, request, closure = portable
    plan = delivery_plan(bundle, request, closure)
    copied = tmp_path / "relocated"
    shutil.copytree(bundle, copied)
    moved = request.model_copy(
        update={
            "bundle": str(copied),
            "requirements": "/other/lock",
            "wheelhouse": "/other/wheels",
            "tag": "another:tag",
        }
    )
    assert delivery_plan(copied, moved, closure) == plan
    assert plan.source.kind == "local"
    contract = json.loads((bundle / "repository-interface.json").read_bytes())
    assert plan.source.repository_digest.model_dump() == contract["repository_digest"]
    assert plan.exposure_plan_digest.model_dump() == contract["exposure_plan_digest"]
    assert plan.application_inputs_digest == identity(prepare(root).application)
    assert {x.name for x in plan.build_tools} == {
        "outerspace-apizr",
        "outerspace-apizr-oci",
    }
    assert plan.generator.name == "outerspace-apizr"
    raw = canonical_bytes(plan)
    for forbidden in (
        str(tmp_path),
        request.docker.socket,
        request.docker.executable,
        "authentication",
        "agent_socket",
        "known_hosts",
        "key_file",
        "trust_store",
        "output_dir",
    ):
        assert forbidden.encode() not in raw
    assert identity(plan) == Digest.of_bytes(raw)
    assert DeliveryPlan.model_validate_json(raw) == plan
    reordered = plan.model_dump(mode="json")
    reordered["build_tools"].reverse()
    assert identity(
        DeliveryPlan.model_validate(dict(reversed(list(reordered.items()))))
    ) == identity(plan)


@pytest.mark.parametrize(
    "field",
    [
        "image_id",
        "inputs_sha256",
        "receipt_sha256",
        "destination",
        "proof_digest",
        "docker",
    ],
)
def test_plan_structurally_forbids_observations_and_operational_inputs(portable, field):
    _, bundle, request, closure = portable
    value = delivery_plan(bundle, request, closure).model_dump(mode="json")
    with pytest.raises(ValidationError):
        DeliveryPlan.model_validate(value | {field: "not a pre-build identity"})


@pytest.mark.parametrize(
    "field",
    [
        "receipt_sha256",
        "artifact_reference",
        "proof_manifest_digest",
        "destination",
        "push",
        "delivery_manifest_digest",
    ],
)
def test_manifest_structurally_forbids_cycles_and_destinations(field):
    value = {
        "delivery_plan_digest": Digest.of_bytes(b"plan").model_dump(),
        "inputs_sha256": "a" * 64,
        "platform": "linux/amd64",
        "image_id": "sha256:" + "b" * 64,
    }
    with pytest.raises(ValidationError):
        DeliveryManifest.model_validate(value | {field: "must not cycle"})


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "resource",
        "dependency",
        "platform",
        "base",
        "wheel",
        "version",
        "policy",
    ],
)
def test_semantic_changes_change_plan_identity(portable, change):
    root, bundle, request, closure = portable
    before = identity(delivery_plan(bundle, request, closure))
    if change in {"source", "resource", "dependency", "policy"}:
        application = None
        if change == "source":
            path = root / "src/formatter.py"
            path.write_text(path.read_text() + "\n# changed source\n")
        elif change == "resource":
            (root / "data/message.txt").write_text("new bytes")
        elif change == "dependency":
            application = ApplicationConfig(
                dependencies=("six==1.16.0",), resources=("data/message.txt",)
            )
        else:
            from apizr.graph import GraphPolicy

            prepared = prepare(root, graph_policy=GraphPolicy(max_ast_nodes=12345))
        if change != "policy":
            prepared = prepare(
                root, **({"application": application} if application else {})
            )
        shutil.rmtree(bundle)
        write_bundle(bundle, render_bundle(prepared, interface="rest"))
    elif change == "platform":
        request = request.model_copy(update={"platform": "linux/arm64"})
    elif change == "base":
        request = request.model_copy(update={"base_image": "python@sha256:" + "d" * 64})
    else:
        closure = (
            closure[0].model_copy(
                update={"sha256": "e" * 64}
                if change == "wheel"
                else {"version": "1.16.0"}
            ),
        )
    assert identity(delivery_plan(bundle, request, closure)) != before


def test_undeclared_resource_and_declaration_order_do_not_change_identity(portable):
    root, bundle, request, closure = portable
    before = identity(delivery_plan(bundle, request, closure))
    (root / "unrelated.json").write_text("not declared")
    (root / ".env").write_text("NEVER PACKAGE")
    shutil.rmtree(bundle)
    write_bundle(bundle, render_bundle(prepare(root), interface="rest"))
    assert identity(delivery_plan(bundle, request, closure)) == before
    extra = LockedDistribution(name="other", version="1.0", sha256="c" * 64)
    assert delivery_plan(bundle, request, (*closure, extra)) == delivery_plan(
        bundle, request, (extra, *closure)
    )
    with pytest.raises(ValidationError, match="Duplicate"):
        delivery_plan(bundle, request, (*closure, *closure))


@pytest.mark.parametrize(
    "artifact",
    [
        "apizr-bundle-provenance.json",
        "repository-interface.json",
        "exposure-plan.json",
        "application-requirements.txt",
        "source/data/message.txt",
        "source/src/formatter.py",
    ],
)
def test_modified_declared_bundle_artifacts_refused(portable, artifact):
    _, bundle, request, closure = portable
    (bundle / artifact).write_bytes(b"substituted")
    with pytest.raises(ValueError):
        delivery_plan(bundle, request, closure)


def test_source_provenance_repository_mismatch_refused(portable):
    root, _, _, _ = portable
    prepared = prepare(root)
    with pytest.raises(ValueError, match="provenance"):
        render_bundle(
            replace(
                prepared,
                source=LocalSource(repository_digest=Digest.of_bytes(b"other")),
            ),
            interface="rest",
        )


@pytest.mark.parametrize(
    "secret",
    [
        "https://user:password@example.com/repo",
        "https://example.com/repo?token=secret",
        "/tmp/repo",
        "ssh://git:password@example.com/repo",
    ],
)
def test_source_provenance_forbids_credential_and_local_path_repositories(secret):
    with pytest.raises(ValueError):
        GitSource(
            repository=secret,
            requested_ref="main",
            resolved_commit="a" * 40,
            subdir=".",
            repository_digest=Digest.of_bytes(b"source"),
        )


def test_historical_bundle_does_not_invent_provenance(portable):
    _, bundle, request, closure = portable
    path = bundle / "apizr-repository-rest.json"
    manifest = json.loads(path.read_text())
    manifest.pop("provenance_digest")
    manifest["artifacts"].pop("apizr-bundle-provenance.json")
    path.write_text(json.dumps(manifest))
    plan = delivery_plan(bundle, request, closure)
    assert plan.source.kind == "unrecorded" and plan.generator is None


def test_wrong_image_plan_label_is_refused(build_inputs, tmp_path):
    fake = Path(build_inputs.docker.executable)
    fake.write_text(
        fake.read_text().replace("Path('plan-state').read_text()", "'0'*64")
    )
    with pytest.raises(BuildError, match="image_unverified"):
        build(build_inputs, workspace=tmp_path)


@pytest.mark.parametrize(
    "change", ["plan", "manifest", "image", "platform", "inputs", "digest", "missing"]
)
def test_build_result_substitutions_fail(build_inputs, tmp_path, change):
    built = build(build_inputs, workspace=tmp_path).model_dump(
        mode="json", by_alias=True
    )
    if change == "plan":
        built["delivery_plan"]["base_image"] = "python@sha256:" + "d" * 64
    elif change == "manifest":
        built["delivery_manifest"]["delivery_plan_digest"]["value"] = "d" * 64
    elif change == "digest":
        built["delivery_manifest_digest"]["value"] = "d" * 64
    elif change == "missing":
        built.pop("delivery_plan")
    else:
        key, value = {
            "image": ("image_id", "sha256:" + "d" * 64),
            "platform": ("platform", "linux/arm64"),
            "inputs": ("inputs_sha256", "d" * 64),
        }[change]
        built[key] = value
    with pytest.raises(ValidationError):
        BuildResult.model_validate(built)


def test_push_request_cannot_substitute_another_image(build_inputs, tmp_path):
    built = build(build_inputs, workspace=tmp_path)
    request = {
        "schema": "apizr.oci-push/v1",
        "image_id": "sha256:" + "d" * 64,
        "platform": built.platform,
        "inputs_sha256": built.inputs_sha256,
        "destination": "registry.test/services/rest:v1",
        "docker": build_inputs.docker.model_dump(),
        "authentication": {"config_file": "/explicit/auth"},
        "delivery_manifest": built.delivery_manifest.model_dump(mode="json"),
    }
    with pytest.raises(ValidationError, match="observed build"):
        PushRequest.model_validate(request)


@pytest.mark.parametrize(
    "name", ["delivery-plan", "delivery-manifest", "bundle-provenance"]
)
def test_published_delivery_schemas(name):
    from jsonschema import Draft202012Validator

    from apizr.delivery import BundleProvenance

    model = {
        "delivery-plan": DeliveryPlan,
        "delivery-manifest": DeliveryManifest,
        "bundle-provenance": BundleProvenance,
    }[name]
    schema = json.loads(
        (
            Path(__file__).parents[2] / f"docs/specs/apizr-{name}-v1.schema.json"
        ).read_bytes()
    )
    assert schema == model.model_json_schema()
    Draft202012Validator.check_schema(schema)


def test_selection_changes_plan_with_identical_repository_bytes(portable):
    root, bundle, request, closure = portable
    source = root / "src/formatter.py"
    source.write_text(
        source.read_text() + "\ndef other() -> str:\n    return 'other'\n"
    )
    shutil.rmtree(bundle)
    write_bundle(bundle, render_bundle(prepare(root), interface="rest"))
    before = delivery_plan(bundle, request, closure)
    policy = root / "exposure.json"
    raw = json.loads(policy.read_bytes())
    raw["selection"]["include"] = ["python:formatter:other"]
    policy.write_text(json.dumps(raw))
    shutil.rmtree(bundle)
    write_bundle(bundle, render_bundle(prepare(root), interface="rest"))
    after = delivery_plan(bundle, request, closure)
    assert before.source == after.source
    assert before.exposure_plan_digest != after.exposure_plan_digest
    assert identity(before) != identity(after)


def test_rehashed_source_provenance_still_requires_repository_binding(portable):
    _, bundle, request, closure = portable
    provenance = bundle / "apizr-bundle-provenance.json"
    value = json.loads(provenance.read_bytes())
    value["source"]["repository_digest"] = Digest.of_bytes(b"other source").model_dump(
        mode="json"
    )
    provenance.write_text(json.dumps(value))
    path = bundle / "apizr-repository-rest.json"
    manifest = json.loads(path.read_bytes())
    digest = Digest.of_bytes(provenance.read_bytes()).model_dump(mode="json")
    manifest["artifacts"][provenance.name] = digest
    manifest["provenance_digest"] = digest
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        delivery_plan(bundle, request, closure)
