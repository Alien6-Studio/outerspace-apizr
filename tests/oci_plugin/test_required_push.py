"""Normal push cannot bypass a required plan; promotion remains digest-only."""

import time

import pytest
from apizr_oci.delivery import delivery_plan
from apizr_oci.model import BuildError
from apizr_oci.push import promote_verified, push

from apizr.delivery import PLAN_LABEL, PROOF_LABEL, DeliveryManifest, identity

from . import test_build, test_delivery, test_push

build_inputs = test_build.build_inputs
portable = test_delivery.portable
request_data = test_push.request_data
transport = test_push.transport


@pytest.fixture
def gated(transport, portable):
    request, calls, remote, image = transport
    _, bundle, build, closure = portable
    plan = delivery_plan(
        bundle, build.model_copy(update={"proof_requirement": "required"}), closure
    )
    manifest = DeliveryManifest(
        delivery_plan_digest=identity(plan),
        image_id=request.image_id,
        platform=request.platform,
        inputs_sha256=request.inputs_sha256,
    )
    image["Config"]["Labels"].update(
        {PLAN_LABEL: identity(plan).value, PROOF_LABEL: "required"}
    )
    request = request.model_copy(
        update={"delivery_plan": plan, "delivery_manifest": manifest}
    )
    return request, calls, remote, image


def test_required_transfer_withholds_tag_and_repeats(gated, tmp_path):
    request, calls, remote, _ = gated
    result = push(request, workspace=tmp_path)
    assert result.published and result.transfer_verified
    assert not result.destination_promoted and not result.delivery_admitted
    assert result.digest_reference in remote and request.destination not in remote
    assert not any(c[:3] == ["buildx", "imagetools", "create"] for c in calls)
    assert push(request, workspace=tmp_path) == result
    assert request.destination not in remote


@pytest.mark.parametrize(
    "fault",
    [
        "omitted-plan",
        "optional-plan",
        "optional-with-new-manifest",
        "missing-manifest",
        "missing-label",
        "different-manifest",
    ],
)
def test_required_image_refuses_policy_or_lineage_substitution(gated, tmp_path, fault):
    request, calls, remote, image = gated
    if fault == "omitted-plan":
        request = request.model_copy(update={"delivery_plan": None})
    elif fault.startswith("optional"):
        plan = request.delivery_plan.model_copy(
            update={"proof_requirement": "optional"}
        )
        update = {"delivery_plan": plan}
        if fault == "optional-with-new-manifest":
            update["delivery_manifest"] = request.delivery_manifest.model_copy(
                update={"delivery_plan_digest": identity(plan)}
            )
        request = request.model_copy(update=update)
    elif fault == "missing-manifest":
        request = request.model_copy(update={"delivery_manifest": None})
    elif fault == "missing-label":
        image["Config"]["Labels"].pop(PROOF_LABEL)
    else:
        request = request.model_copy(
            update={
                "delivery_manifest": request.delivery_manifest.model_copy(
                    update={"inputs_sha256": "0" * 64}
                )
            }
        )
    with pytest.raises(BuildError):
        push(request, workspace=tmp_path)
    assert not remote and not any(c[:2] == ["image", "push"] for c in calls)


def test_verified_promotion_and_idempotency(gated, tmp_path):
    request, calls, remote, _ = gated
    result = push(request, workspace=tmp_path)
    verified = (result.config_digest, result.manifest_digest)
    promote_verified(request, tmp_path, verified, time.monotonic() + 10)
    assert remote[request.destination] == remote[result.digest_reference]
    calls.clear()
    promote_verified(request, tmp_path, verified, time.monotonic() + 10)
    assert not any(c[:3] == ["buildx", "imagetools", "create"] for c in calls)


@pytest.mark.parametrize("fault", ["digest-before", "conflict", "after", "interrupted"])
def test_promotion_refusals_and_uncertainty(gated, tmp_path, monkeypatch, fault):
    request, calls, remote, _ = gated
    result = push(request, workspace=tmp_path)
    verified = (result.config_digest, result.manifest_digest)
    original = test_push.mod.remote_identity

    def observation(req, work, reference, *args, **kwargs):
        if fault == "digest-before" and reference == result.digest_reference:
            return ("sha256:" + "0" * 64, verified[1])
        if fault == "conflict" and reference == request.destination:
            return ("sha256:" + "0" * 64, verified[1])
        if (
            fault == "after"
            and reference == request.destination
            and reference in remote
        ):
            return None
        return original(req, work, reference, *args, **kwargs)

    monkeypatch.setattr(test_push.mod, "remote_identity", observation)
    if fault == "interrupted":
        run = test_push.mod.run

        def interrupted(req, work, args, *rest, **kw):
            result = run(req, work, args, *rest, **kw)
            if args[:3] == ["buildx", "imagetools", "create"]:
                raise BuildError("cancelled")
            return result

        monkeypatch.setattr(test_push.mod, "run", interrupted)
    with pytest.raises(
        BuildError,
        match="remote_state_unconfirmed"
        if fault in {"after", "interrupted"}
        else "remote_",
    ):
        promote_verified(request, tmp_path, verified, time.monotonic() + 10)
    assert (request.destination in remote) == (fault in {"after", "interrupted"})
