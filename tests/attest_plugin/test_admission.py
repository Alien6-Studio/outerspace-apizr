"""Selected remote proof, native verification, and final promotion boundary."""

import json
from pathlib import Path

import pytest
import test_delivery as delivery_fixtures
from apizr_attest import admission, artifacts, delivery
from apizr_attest.model import AdmitRequest, AttestError
from apizr_oci.model import BuildError
from apizr_oci.oras import OCI_MANIFEST, sha

from apizr.delivery import PLAN_LABEL, PROOF_LABEL, DeliveryPlan, identity

mocked = delivery_fixtures.mocked
transversal = delivery_fixtures.transversal


@pytest.fixture
def required(transversal, tmp_path, monkeypatch):
    built = json.loads(Path(transversal.build_result).read_bytes())
    plan = DeliveryPlan.model_validate(
        built["delivery_plan"] | {"proof_requirement": "required"}
    )
    built["delivery_plan"] = plan.model_dump(mode="json")
    built["delivery_manifest"]["delivery_plan_digest"] = identity(plan).model_dump()
    from apizr.delivery import DeliveryManifest

    manifest = DeliveryManifest.model_validate(built["delivery_manifest"])
    built["delivery_manifest_digest"] = identity(manifest).model_dump()
    pushed = json.loads(Path(transversal.push_result).read_bytes())
    pushed.update(
        delivery_plan_digest=identity(plan).model_dump(),
        delivery_manifest_digest=identity(manifest).model_dump(),
        proof_requirement="required",
        transfer_verified=True,
        destination_promoted=False,
        delivery_admitted=False,
    )
    Path(transversal.build_result).write_bytes(delivery.canonical(built))
    Path(transversal.push_result).write_bytes(delivery.canonical(pushed))
    work = tmp_path / "signing"
    work.mkdir()
    verification = delivery.execute_attest(transversal, work)
    proof = Path(transversal.output_dir)
    files = {n: (proof / n).read_bytes() for n in delivery.proof_files(proof)}
    image = files["delivery/oci-manifest.json"]
    subject = {
        "mediaType": OCI_MANIFEST,
        "digest": pushed["manifest_digest"],
        "size": len(image),
    }
    artifact = {
        "schemaVersion": 2,
        "mediaType": OCI_MANIFEST,
        "artifactType": artifacts.ARTIFACT_TYPE,
        "config": artifacts.EMPTY,
        "annotations": artifacts.ANNOTATIONS,
        "subject": subject,
        "layers": [
            {
                "mediaType": artifacts.LAYER_TYPE,
                "digest": sha(files[n]),
                "size": len(files[n]),
                "annotations": {"org.opencontainers.image.title": n},
            }
            for n in sorted(files)
        ],
    }
    artifact_raw = delivery.canonical(artifact)
    desc = {
        "mediaType": OCI_MANIFEST,
        "digest": sha(artifact_raw),
        "size": len(artifact_raw),
    }
    config = {
        "os": "linux",
        "architecture": "amd64",
        "config": {
            "User": "65532:65532",
            "Labels": {
                admission.LABEL: pushed["inputs_sha256"],
                PLAN_LABEL: identity(plan).value,
                PROOF_LABEL: "required",
            },
        },
    }
    repository = pushed["destination"].rsplit(":", 1)[0]
    selected = repository + "@" + desc["digest"]
    state = {
        "promotions": 0,
        "discovered": True,
        "artifact": artifact,
        "config": config,
        "files": files,
        "verification": verification,
        "native_checks": 0,
    }

    class Registry:
        def manifest(self, reference):
            if reference == transversal.expected_reference:
                return image, subject
            assert reference == selected
            return delivery.canonical(state["artifact"]), desc

        def discover(self, artifact_type):
            return (
                [
                    desc
                    | {
                        "reference": selected,
                        "artifact_type": artifact_type,
                        "verified": False,
                    }
                ]
                if state["discovered"]
                else []
            )

        def blob(self, descriptor):
            if descriptor["digest"] == pushed["config_digest"]:
                return delivery.canonical(state["config"])
            return next(
                v for v in state["files"].values() if sha(v) == descriptor["digest"]
            )

    monkeypatch.setattr(artifacts, "registry", lambda *a: Registry())

    # Preserve the shared proof parser, binding checks and strict native verdict;
    # only native executable identity/trust copying are supplied by the fixture.
    def check(request, work, proof, deadline, original):
        state["native_checks"] += 1
        return delivery.verified(
            request, Path("/bin/true"), proof, Path(transversal.trust_store), deadline
        )

    monkeypatch.setattr(artifacts, "check_proof", check)
    monkeypatch.setattr(admission, "authentication", lambda *a: None)
    monkeypatch.setattr(admission, "secure_daemon", lambda *a: None)

    def promote(*a):
        state["promotions"] += 1

    monkeypatch.setattr(admission, "promote_verified", promote)
    request = AdmitRequest.model_validate(
        {
            **transversal.model_dump(
                by_alias=True,
                include={
                    "expected_reference",
                    "expected_signer",
                    "trust_store",
                    "tool",
                    "docker",
                    "push_result",
                },
            ),
            "schema": "apizr.admit-delivery/v1",
            "destination": pushed["destination"],
            "delivery_manifest": manifest.model_dump(mode="json"),
            "artifact_reference": selected,
            "transport": {
                "tool": {
                    "executable": "/explicit/oras",
                    "version": "1.3.4",
                    "sha256": "0" * 64,
                },
                "authentication": {"config_file": "/explicit/auth"},
            },
        }
    )
    return request, state


def execute(required, tmp_path):
    work = tmp_path / "admitting"
    work.mkdir()
    return admission.execute_admit(required[0], work)


def test_remote_verification_precedes_admission(required, tmp_path):
    result = execute(required, tmp_path)
    assert (
        result.state == "admitted"
        and result.delivery_admitted
        and result.destination_promoted
    )
    assert required[1]["native_checks"] == required[1]["promotions"] == 1
    assert result.proof_artifact_reference == required[0].artifact_reference
    assert str(tmp_path) not in result.model_dump_json()


@pytest.mark.parametrize(
    "fault",
    [
        "undiscoverable",
        "subject",
        "manifest",
        "optional",
        "missing-lineage",
        "fabricated-publish",
        "uncertain-publish",
        "wrong-transfer",
        "image-plan",
        "image-inputs",
        "image-policy",
        "image-platform",
        "image-user",
        "warnings",
        "skipped",
        "signer",
        "another-proof-plan",
    ],
)
def test_substitution_never_promotes(required, tmp_path, monkeypatch, fault):
    request, state = required
    if fault == "undiscoverable":
        state["discovered"] = False
    elif fault == "subject":
        state["artifact"]["subject"] = state["artifact"]["subject"] | {
            "digest": "sha256:" + "9" * 64
        }
    elif fault == "manifest":
        request = request.model_copy(
            update={
                "delivery_manifest": request.delivery_manifest.model_copy(
                    update={"inputs_sha256": "9" * 64}
                )
            }
        )
    elif fault in {
        "optional",
        "missing-lineage",
        "fabricated-publish",
        "uncertain-publish",
        "wrong-transfer",
    }:
        pushed = json.loads(Path(request.push_result).read_bytes())
        if fault == "optional":
            pushed.update(proof_requirement="optional", destination_promoted=True)
        elif fault == "missing-lineage":
            pushed.pop("delivery_plan_digest")
        elif fault == "wrong-transfer":
            pushed["destination"] += "-other"
        else:
            pushed = {
                "schema": "apizr.published-proof/v1",
                "state": "remote_state_unconfirmed"
                if fault == "uncertain-publish"
                else "verified",
                "artifact_reference": request.artifact_reference,
            }
        Path(request.push_result).write_text(json.dumps(pushed))
    elif fault.startswith("image-"):
        config = state["config"]
        if fault == "image-platform":
            config["architecture"] = "arm64"
        elif fault == "image-user":
            config["config"]["User"] = "root"
        else:
            config["config"]["Labels"][
                {
                    "image-plan": PLAN_LABEL,
                    "image-inputs": admission.LABEL,
                    "image-policy": PROOF_LABEL,
                }[fault]
            ] = "invalid"
    elif fault == "another-proof-plan":
        # A modified valid-shaped build cannot substitute the selected immutable plan.
        built = json.loads(state["files"]["delivery/build.json"])
        built["delivery_plan"]["base_image"] = "python@sha256:" + "9" * 64
        state["files"]["delivery/build.json"] = delivery.canonical(built)
        for layer in state["artifact"]["layers"]:
            if (
                layer["annotations"]["org.opencontainers.image.title"]
                == "delivery/build.json"
            ):
                layer.update(
                    digest=sha(state["files"]["delivery/build.json"]),
                    size=len(state["files"]["delivery/build.json"]),
                )
    else:
        from test_delivery import verdict

        report = verdict()
        if fault == "warnings":
            report["warnings"] = ["warning"]
        elif fault == "skipped":
            report["checks"][0]["status"] = "skip"
        else:
            report["signed_by"] = "9" * 64
        monkeypatch.setattr(delivery, "run", lambda *a: json.dumps(report).encode())
    with pytest.raises((AttestError, ValueError, BuildError)):
        execute((request, state), tmp_path)
    assert state["promotions"] == 0


@pytest.mark.parametrize("code", ["remote_state_unconfirmed", "remote_image_conflict"])
def test_promotion_uncertainty_is_not_admission(required, tmp_path, monkeypatch, code):
    def fail(*args):
        raise BuildError(code)

    monkeypatch.setattr(admission, "promote_verified", fail)
    if code == "remote_image_conflict":
        with pytest.raises(BuildError, match=code):
            execute(required, tmp_path)
    else:
        result = execute(required, tmp_path)
        assert (
            result.state == code
            and result.delivery_admitted is False
            and result.destination_promoted is None
        )


def test_explicit_selection_and_same_repository_required(required):
    raw = required[0].model_dump(by_alias=True)
    for change in (
        {"artifact_reference": None},
        {
            "artifact_reference": raw["artifact_reference"].replace(
                "/services/", "/other/"
            )
        },
        {"destination": raw["destination"].replace("/services/", "/other/")},
        {"key_file": "/private/key"},
    ):
        with pytest.raises(ValueError):
            AdmitRequest.model_validate(raw | change)


def test_admit_typed_api_protocol_and_result_states(
    required, tmp_path, monkeypatch, capsys
):
    import io
    import sys
    from types import SimpleNamespace

    from apizr_attest import api, protocol
    from apizr_attest.model import AdmissionResult

    request, _ = required
    reply = execute(required, tmp_path)
    monkeypatch.setattr(
        api,
        "invoke_extension",
        lambda *a, **kw: SimpleNamespace(result=reply.model_dump(by_alias=True)),
    )
    assert api.admit(request) == reply
    monkeypatch.setattr(protocol, "execute_admit", lambda *a: reply)
    payload = {
        "protocol": "apizr.extension/v1",
        "request_id": "0" * 32,
        "operation": "admit",
        "arguments": request.model_dump(by_alias=True),
    }
    monkeypatch.setattr(
        sys, "stdin", SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode()))
    )
    assert protocol.main() == 0
    assert json.loads(capsys.readouterr().out)["result"]["state"] == "admitted"
    for change in (
        {"delivery_admitted": False},
        {"destination_promoted": False},
        {"state": "remote_state_unconfirmed"},
    ):
        with pytest.raises(ValueError):
            AdmissionResult.model_validate(reply.model_dump(by_alias=True) | change)


def test_valid_remote_proof_for_another_expected_plan_is_refused(required, tmp_path):
    """The selected proof stays internally valid; the expected plan is different."""
    from apizr.capabilities.model import Digest

    request, state = required
    expected_manifest = request.delivery_manifest.model_copy(
        update={"delivery_plan_digest": Digest.of_bytes(b"another reviewed plan")}
    )
    pushed = json.loads(Path(request.push_result).read_bytes())
    pushed.update(
        delivery_plan_digest=expected_manifest.delivery_plan_digest.model_dump(),
        delivery_manifest_digest=identity(expected_manifest).model_dump(),
    )
    Path(request.push_result).write_text(json.dumps(pushed))
    request = request.model_copy(update={"delivery_manifest": expected_manifest})
    with pytest.raises(AttestError, match="admission_lineage_mismatch"):
        execute((request, state), tmp_path)
    assert state["native_checks"] == 1
    assert state["promotions"] == 0
