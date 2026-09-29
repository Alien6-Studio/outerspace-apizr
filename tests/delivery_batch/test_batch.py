"""Coordinator boundary: identity, independent effects, resume and fixed output."""

import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest

from apizr.capabilities.model import Digest
from apizr.delivery import DeliveryManifest, DeliveryPlan, identity
from apizr.delivery_batch import (
    BatchError,
    BatchRequest,
    BatchResult,
    deliver_batch,
    operations,
)
from apizr.delivery_batch.models import MAX_DESTINATIONS
from apizr.delivery_results import BuildResult, PushResult
from apizr.extension_runtime import InvocationCancelled, PluginFailed
from apizr.operator_policy import AuthorizationDenied

D = Digest(algorithm="sha256", value="b" * 64)
IMAGE = "sha256:" + "a" * 64
MANIFEST = "sha256:" + "c" * 64
ARTIFACT = "sha256:" + "d" * 64
SIGNER = "e" * 64


def request(tmp_path, required=True, count=3):
    fields = {name: D for name in DeliveryPlan.model_fields if name.endswith("_digest")}
    plan = DeliveryPlan(
        **fields,
        proof_requirement="required" if required else "optional",
        source={"kind": "local", "repository_digest": D},
        interface="rest",
        dependency_closure=({"name": "six", "version": "1.17.0", "sha256": "a" * 64},),
        build_tools=tuple(
            {"name": name, "version": "0.4.1rc1"}
            for name in ("outerspace-apizr", "outerspace-apizr-oci")
        ),
        platform="linux/amd64",
        base_image="python@sha256:" + "a" * 64,
    )
    manifest = DeliveryManifest(
        delivery_plan_digest=identity(plan),
        image_id=IMAGE,
        platform=plan.platform,
        inputs_sha256="b" * 64,
    )
    build = BuildResult(
        tag="service:local",
        image_id=IMAGE,
        platform=plan.platform,
        inputs_sha256=manifest.inputs_sha256,
        delivery_plan=plan,
        delivery_manifest=manifest,
        delivery_manifest_digest=identity(manifest),
    )
    destinations = []
    for i in range(count):
        destinations.append(
            {
                "push": {
                    "schema": "apizr.oci-push/v1",
                    "image_id": IMAGE,
                    "platform": plan.platform,
                    "inputs_sha256": manifest.inputs_sha256,
                    "delivery_plan": plan.model_dump(mode="json"),
                    "delivery_manifest": manifest.model_dump(mode="json"),
                    "destination": f"registry.example/team/service-{i}:v1",
                    "docker": {
                        "executable": "/private/docker",
                        "socket": "/private/daemon.sock",
                    },
                    "authentication": {"config_file": f"/private/auth-{i}.json"},
                },
                "proof": {
                    "verification": {
                        "expected_signer": SIGNER,
                        "trust_store": "/private/trust",
                        "tool": {
                            "executable": "/private/attest",
                            "version": "0.1.0",
                            "sha256": "f" * 64,
                        },
                    },
                    "signing": {
                        "key_file": "/private/key",
                        "key_id": "e" * 32,
                        "tsa_url": "https://tsa.example/timestamp",
                    },
                    "transport": {
                        "authentication": {"config_file": f"/private/oras-{i}.json"},
                        "tool": {
                            "executable": "/private/oras",
                            "version": "1.3.4",
                            "sha256": "f" * 64,
                        },
                    },
                }
                if required
                else None,
            }
        )
    return BatchRequest.model_validate_json(
        json.dumps(
            {
                "schema": "apizr.delivery-batch-request/v1",
                "build": build.model_dump(mode="json", by_alias=True),
                "destinations": destinations,
                "evidence_root": str(tmp_path / "evidence"),
            }
        )
    )


class Managed:
    def __init__(self):
        self.calls = []
        self.fail = None
        self.denied = None
        self.tags = {}
        self.transfers = {}
        self.proofs = {}
        self.cancel_after = None
        self.observe_state = None
        self.uncertain_publish = False
        self.uncertain_admit = False

    def __call__(self, plugin, operation, data, **kwargs):
        assert operation != "build"
        destination = data.get("destination", data.get("push", {}).get("destination"))
        reference = data.get("expected_reference")
        repo = destination.rsplit(":", 1)[0] if destination else reference.split("@")[0]
        self.calls.append((operation, repo, data))
        if self.denied == (operation, repo):
            raise AuthorizationDenied("operator_repository_denied")
        if self.fail == (operation, repo):
            raise PluginFailed()
        if operation == "push":
            required = data["delivery_plan"].get("proof_requirement") == "required"
            result = PushResult(
                destination=destination,
                digest_reference=repo + "@" + MANIFEST,
                platform=data["platform"],
                image_id=IMAGE,
                config_digest=IMAGE,
                manifest_digest=MANIFEST,
                inputs_sha256="b" * 64,
                delivery_plan_digest=data["delivery_manifest"]["delivery_plan_digest"],
                delivery_manifest_digest=identity(
                    DeliveryManifest.model_validate(data["delivery_manifest"])
                ),
                proof_requirement="required" if required else "optional",
                transfer_verified=True,
                destination_promoted=not required,
                delivery_admitted=False,
            ).model_dump(mode="json", by_alias=True)
            self.transfers[repo] = result
            if not required:
                self.tags[repo] = MANIFEST
        elif operation == "observe":
            state = self.observe_state or (
                "verified"
                if self.tags.get(repo) == MANIFEST
                else "conflict"
                if repo in self.tags
                else "absent"
            )
            result = {
                "destination": destination,
                "state": state,
                "image": {
                    "digest_reference": repo + "@" + MANIFEST,
                    "config_digest": IMAGE,
                    "manifest_digest": MANIFEST,
                }
                if repo in self.transfers
                else None,
            }
        elif operation in {"attest", "verify"}:
            if operation == "attest":
                Path(data["output_dir"]).mkdir()
                pushed = self.transfers[repo]
                self.proofs[repo] = {
                    "reference": reference,
                    "manifest_digest": MANIFEST,
                    "signer": SIGNER,
                    "receipt_sha256": "f" * 64,
                    "attest_tool": {"version": "0.1.0", "sha256": "f" * 64},
                    "checks": dict.fromkeys(
                        (
                            "consistency",
                            "recompute",
                            "schema",
                            "signature",
                            "timestamp",
                        ),
                        "pass",
                    ),
                    "delivery_plan_digest": pushed["delivery_plan_digest"],
                    "delivery_manifest_digest": pushed["delivery_manifest_digest"],
                }
            result = self.proofs[repo]
        elif operation == "publish":
            result = {
                "image_reference": reference,
                "image_digest": MANIFEST,
                "artifact_reference": repo + "@" + ARTIFACT,
                "artifact_manifest_digest": ARTIFACT,
                "receipt_sha256": "f" * 64,
                "verification": self.proofs[repo],
            }
            if self.uncertain_publish:
                result.update(
                    state="remote_state_unconfirmed",
                    receipt_published=False,
                    artifact_reference=None,
                    artifact_manifest_digest=None,
                )
        elif operation == "admit":
            self.tags[repo] = MANIFEST
            pushed = self.transfers[repo]
            result = {
                "destination": destination,
                "image_reference": reference,
                "delivery_plan_digest": pushed["delivery_plan_digest"],
                "delivery_manifest_digest": pushed["delivery_manifest_digest"],
                "proof_artifact_reference": data["artifact_reference"],
                "proof_artifact_manifest_digest": ARTIFACT,
                "receipt_sha256": "f" * 64,
                "signer": SIGNER,
            }
            if self.uncertain_admit:
                result.update(
                    state="remote_state_unconfirmed",
                    destination_promoted=None,
                    delivery_admitted=False,
                )
        else:
            raise AssertionError(operation)
        if self.cancel_after == (operation, repo):
            kwargs["cancel"].set()
        return SimpleNamespace(result=result)


@pytest.fixture
def managed(monkeypatch):
    value = Managed()
    monkeypatch.setattr(operations, "run_extension", value)
    return value


@pytest.mark.parametrize("required", [False, True])
def test_complete_and_resume_never_build_or_replay(tmp_path, managed, required):
    batch = request(tmp_path, required)
    result = deliver_batch(batch)
    assert result.state == "complete" and result.exit_code == 0
    assert [o.destination for o in result.outcomes] == [
        d.push.destination for d in batch.destinations
    ]
    initial = list(managed.calls)
    managed.calls.clear()
    resumed = deliver_batch(batch, resume=True)
    assert resumed == result
    assert {op for op, _, _ in managed.calls} == (
        {"observe", "admit"} if required else {"observe"}
    )
    assert len([c for c in initial if c[0] == "push"]) == 3
    raw = resumed.model_dump_json(by_alias=True)
    assert all(
        value not in raw
        for value in (
            "/private/",
            str(tmp_path),
            "key_file",
            "trust_store",
            "authentication",
        )
    )


@pytest.mark.parametrize("stage", ["push", "attest", "publish", "admit"])
def test_grant_failure_is_local_and_resume_reuses_prior_stages(
    tmp_path, managed, stage
):
    batch = request(tmp_path)
    repo = batch.destinations[1].push.destination.rsplit(":", 1)[0]
    managed.denied = stage, repo
    result = deliver_batch(batch)
    assert result.state == "partial" and result.exit_code == 1
    assert [o.state for o in result.outcomes] == ["complete", "failed", "complete"]
    assert result.outcomes[1].diagnostic == "authorization_refused"
    managed.denied = None
    managed.calls.clear()
    assert deliver_batch(batch, resume=True).state == "complete"
    middle = [op for op, r, _ in managed.calls if r == repo]
    stages = ["push", "attest", "publish", "admit"]
    assert all(op not in middle for op in stages[: stages.index(stage)])
    if stage == "publish":
        assert "verify" in middle


@pytest.mark.parametrize("count", [0, MAX_DESTINATIONS + 1])
def test_bound_before_effects(tmp_path, managed, count):
    with pytest.raises(ValueError):
        request(tmp_path, count=count)
    assert not managed.calls


@pytest.mark.parametrize("alias", [False, True])
def test_duplicate_refused_before_effects(tmp_path, managed, alias):
    raw = request(tmp_path).model_dump(mode="json", by_alias=True)
    raw["destinations"][1]["push"]["destination"] = raw["destinations"][0]["push"][
        "destination"
    ]
    if alias:
        raw["destinations"][0]["push"]["destination"] = "docker.io/team/service:v1"
        raw["destinations"][1]["push"]["destination"] = (
            "index.docker.io/team/service:v1"
        )
    with pytest.raises(ValueError):
        BatchRequest.model_validate_json(json.dumps(raw))
    assert not managed.calls


@pytest.mark.parametrize(
    "field", ["image_id", "inputs_sha256", "delivery_manifest", "delivery_plan"]
)
def test_shared_build_mismatch_before_effects(tmp_path, managed, field):
    raw = request(tmp_path).model_dump(mode="json", by_alias=True)
    if field in {"image_id", "inputs_sha256"}:
        raw["destinations"][1]["push"][field] = (
            "sha256:" if field == "image_id" else ""
        ) + "0" * 64
    else:
        raw["destinations"][1]["push"][field] = None
    with pytest.raises(ValueError):
        BatchRequest.model_validate_json(json.dumps(raw))
    assert not managed.calls


@pytest.mark.parametrize(
    "fault",
    [
        "build",
        "destination",
        "order",
        "proof_requirement",
        "manifest",
        "proof-secret",
        "fabricated-complete",
    ],
)
def test_resume_substitution_before_effects(tmp_path, managed, fault):
    batch = request(tmp_path)
    deliver_batch(batch)
    saved = Path(batch.evidence_root) / "batch.json"
    raw = json.loads(saved.read_bytes())
    if fault == "build":
        raw["build"]["image_id"] = "sha256:" + "0" * 64
    elif fault == "destination":
        raw["outcomes"][1]["destination"] = "other.example/team/image:v1"
    elif fault == "order":
        raw["outcomes"].reverse()
    elif fault == "proof_requirement":
        raw["proof_requirement"] = "optional"
    elif fault == "manifest":
        raw["delivery_manifest_digest"]["value"] = "0" * 64
    elif fault == "proof-secret":
        raw["outcomes"][0]["proof"]["signer"] = "/private/SECRET"
    else:
        raw["outcomes"][0]["admission"] = None
    saved.write_text(json.dumps(raw))
    managed.calls.clear()
    with pytest.raises(BatchError):
        deliver_batch(batch, resume=True)
    assert not managed.calls


@pytest.mark.parametrize("required", [False, True])
@pytest.mark.parametrize("state", ["conflict", "absent", "remote_state_unconfirmed"])
def test_completed_destination_reobserved_without_replay(
    tmp_path, managed, required, state
):
    batch = request(tmp_path, required)
    deliver_batch(batch)
    managed.observe_state = state
    managed.calls.clear()
    result = deliver_batch(batch, resume=True)
    assert result.state == "failed" and result.exit_code == 1
    assert {op for op, _, _ in managed.calls} == {"observe"}


@pytest.mark.parametrize("exception", [False, True])
def test_uncertain_publication_requires_explicit_selection(
    tmp_path, managed, exception
):
    batch = request(tmp_path, count=1)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    managed.uncertain_publish = not exception
    managed.fail = ("publish", repo) if exception else None
    result = deliver_batch(batch)
    assert result.state == "failed"
    assert result.outcomes[0].state == "remote_state_unconfirmed"
    managed.fail = None
    managed.uncertain_publish = False
    managed.calls.clear()
    waiting = deliver_batch(batch, resume=True)
    assert waiting.outcomes[0].diagnostic == "proof_selection_required"
    assert not any(
        op in {"push", "attest", "publish", "admit"} for op, _, _ in managed.calls
    )
    raw = batch.model_dump(mode="json", by_alias=True)
    raw["destinations"][0]["selected_artifact"] = repo + "@" + ARTIFACT
    recovered = deliver_batch(
        BatchRequest.model_validate_json(json.dumps(raw)), resume=True
    )
    assert recovered.state == "complete"
    assert not any(
        op in {"build", "push", "attest", "publish"} for op, _, _ in managed.calls
    )


def test_uncertain_admission_reobserves_and_reverifies_same_proof(tmp_path, managed):
    batch = request(tmp_path, count=1)
    managed.uncertain_admit = True
    result = deliver_batch(batch)
    assert result.outcomes[0].last_confirmed_stage == "proof_published"
    assert result.outcomes[0].state == "remote_state_unconfirmed"
    managed.uncertain_admit = False
    managed.calls.clear()
    assert deliver_batch(batch, resume=True).state == "complete"
    assert [op for op, _, _ in managed.calls] == ["observe", "admit"]


def test_uncertain_transfer_requires_observation_and_known_identity(tmp_path, managed):
    batch = request(tmp_path, count=1)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    managed.fail = "push", repo
    result = deliver_batch(batch)
    assert result.outcomes[0].state == "remote_state_unconfirmed"
    managed.fail = None
    managed.calls.clear()
    assert (
        deliver_batch(batch, resume=True).outcomes[0].diagnostic
        == "transfer_identity_required"
    )
    assert [op for op, _, _ in managed.calls] == ["observe"]


@pytest.mark.parametrize("during", [False, True])
def test_cancel_preserves_completed_and_does_not_start_later(
    tmp_path, managed, during, monkeypatch
):
    batch = request(tmp_path)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    if not during:
        managed.cancel_after = "admit", repo
    else:
        real = managed.__call__

        def interrupted(plugin, operation, data, **kw):
            if (
                operation == "push"
                and data["destination"] == batch.destinations[1].push.destination
            ):
                raise InvocationCancelled()
            return real(plugin, operation, data, **kw)

        monkeypatch.setattr(operations, "run_extension", interrupted)
    result = deliver_batch(batch)
    assert result.state == "cancelled" and result.exit_code == 130
    assert result.outcomes[0].state == "complete"
    assert result.outcomes[-1].state == "not_started"
    assert not any(r.endswith("service-2") for _, r, _ in managed.calls)


def test_precancelled_has_all_destinations_and_no_calls(tmp_path, managed):
    event = Event()
    event.set()
    result = deliver_batch(request(tmp_path), cancel=event)
    assert result.state == "cancelled"
    assert not managed.calls and len(result.outcomes) == 3


def test_evidence_does_not_overwrite_other_build_or_symlinks(tmp_path, managed):
    batch = request(tmp_path)
    root = Path(batch.evidence_root)
    root.mkdir()
    (root / "build.json").write_text("{}")
    with pytest.raises(BatchError):
        deliver_batch(batch)
    assert not managed.calls
    (root / "build.json").unlink()
    (root / "build.json").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(BatchError):
        deliver_batch(batch)
    assert not managed.calls


def test_aggregate_cannot_claim_complete_on_partial(tmp_path, managed):
    batch = request(tmp_path)
    managed.denied = "push", batch.destinations[1].push.destination.rsplit(":", 1)[0]
    result = deliver_batch(batch)
    raw = result.model_dump(mode="json", by_alias=True) | {"state": "complete"}
    with pytest.raises(ValueError):
        BatchResult.model_validate_json(json.dumps(raw))


def test_all_refused_is_failed(tmp_path, managed, monkeypatch):
    def denied(*a, **kw):
        raise AuthorizationDenied("operator_policy_required")

    monkeypatch.setattr(operations, "run_extension", denied)
    result = deliver_batch(request(tmp_path))
    assert result.state == "failed" and result.exit_code == 1
    assert all(o.diagnostic == "authorization_refused" for o in result.outcomes)


def test_managed_authorization_is_independent_at_every_destination_stage(
    tmp_path, managed, monkeypatch
):
    from contextlib import contextmanager

    from apizr.local_plugins import activation
    from apizr.local_plugins.models import Installation
    from apizr.operator_policy import OperatorPolicy, PluginIdentity

    batch = request(tmp_path)
    bindings = {}
    for name, module in (
        (operations.OCI, "apizr_oci.protocol"),
        (operations.ATTEST, "apizr_attest.protocol"),
    ):
        bindings[name] = Installation.model_validate_json(
            json.dumps(
                {
                    "schema": "apizr.extension-manifest/v1",
                    "name": name,
                    "version": "0.4.1rc1",
                    "module": module,
                    "protocol": "apizr.extension/v1",
                    "sha256": "a" * 64,
                    "environment_id": "b" * 32,
                    "python": "/private/python",
                    "lock_sha256": "c" * 64,
                    "dependencies": [],
                }
            )
        )
    grants = []
    for i, destination in enumerate(batch.destinations):
        for operation in ("push", "attest", "publish", "admit"):
            if i == 1 and operation == "publish":
                continue
            name = operations.OCI if operation == "push" else operations.ATTEST
            grant = {
                "plugin": PluginIdentity.from_installation(bindings[name]).model_dump(
                    mode="json"
                ),
                "operation": operation,
                "repository": destination.push.destination.rsplit(":", 1)[0],
                "permissions": ["registry.read", "registry.publish"],
            }
            if operation == "attest":
                grant.update(destination.proof.signing.model_dump())
                grant.update(
                    expected_signer=SIGNER,
                    permissions=["registry.read", "receipt.sign", "timestamp.request"],
                )
            grants.append(grant)
    policy = OperatorPolicy.model_validate_json(
        json.dumps({"schema": "apizr.operator-policy/v1", "grants": grants})
    )

    @contextmanager
    def admitted(name, **kw):
        yield bindings[name], 0

    def invoke(python, module, operation, data, **kw):
        name = operations.OCI if module == "apizr_oci.protocol" else operations.ATTEST
        return managed(name, operation, data, **kw)

    monkeypatch.setattr(activation, "admitted_extension", admitted)
    monkeypatch.setattr(activation, "invoke_extension", invoke)
    monkeypatch.setattr(operations, "run_extension", activation.run_extension)
    result = deliver_batch(batch, operator_policy=policy)
    assert result.state == "partial"
    assert result.outcomes[1].last_confirmed_stage == "proof_created"
    assert result.outcomes[1].diagnostic == "authorization_refused"
    assert all(
        not (op == "publish" and repo.endswith("service-1"))
        for op, repo, _ in managed.calls
    )
    assert result.outcomes[2].state == "complete"


def test_cli_partial_json_and_exit_status(tmp_path, managed, capsys):
    from apizr.cli import main

    batch = request(tmp_path, required=False)
    managed.denied = "push", batch.destinations[1].push.destination.rsplit(":", 1)[0]
    file = tmp_path / "request.json"
    file.write_text(batch.model_dump_json(by_alias=True))
    policy = tmp_path / "policy.json"
    policy.write_text('{"schema":"apizr.operator-policy/v1","grants":[]}')
    assert (
        main(
            [
                "delivery",
                "run",
                "--request",
                str(file),
                "--operator-policy",
                str(policy),
            ]
        )
        == 1
    )
    stdout, stderr = capsys.readouterr()
    assert not stderr and json.loads(stdout)["state"] == "partial"
    managed.denied = None
    assert (
        main(
            [
                "delivery",
                "resume",
                "--request",
                str(file),
                "--operator-policy",
                str(policy),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["state"] == "complete"


@pytest.mark.parametrize("fault", ["missing", "invalid", "duplicate-key"])
def test_cli_fixed_preflight_error(tmp_path, capsys, fault):
    from apizr.cli import main

    path = tmp_path / "request.json"
    if fault != "missing":
        path.write_text(
            '{"secret":"PRIVATE"}' if fault == "invalid" else '{"a":1,"a":2}'
        )
    assert (
        main(
            [
                "delivery",
                "run",
                "--request",
                str(path),
                "--operator-policy",
                str(tmp_path / "missing"),
            ]
        )
        == 2
    )
    stdout, stderr = capsys.readouterr()
    assert (
        not stdout and stderr == "apizr delivery: batch_request_or_evidence_invalid\n"
    )


def test_core_coordinator_does_not_import_optional_implementations():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from apizr.delivery_batch import deliver_batch; assert not any(m.startswith(('apizr_oci','apizr_attest')) for m in sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_optional_uncertain_upload_recovery_reuses_explicit_digest(tmp_path, managed):
    batch = request(tmp_path, required=False, count=1)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    managed.fail = "push", repo
    deliver_batch(batch)
    managed.fail = None
    managed.transfers[repo] = True
    raw = batch.model_dump(mode="json", by_alias=True)
    raw["destinations"][0]["recovery_reference"] = repo + "@" + MANIFEST
    managed.calls.clear()
    result = deliver_batch(
        BatchRequest.model_validate_json(json.dumps(raw)), resume=True
    )
    assert result.state == "complete"
    assert [op for op, _, _ in managed.calls] == ["observe", "push"]
    assert managed.calls[-1][2]["resume_reference"] == repo + "@" + MANIFEST


def test_selected_remote_proof_can_resume_without_local_proof_or_signing(
    tmp_path, managed
):
    batch = request(tmp_path, count=1)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    managed.denied = "attest", repo
    result = deliver_batch(batch)
    assert result.outcomes[0].last_confirmed_stage == "transferred"
    raw = batch.model_dump(mode="json", by_alias=True)
    raw["destinations"][0]["selected_artifact"] = repo + "@" + ARTIFACT
    managed.calls.clear()
    recovered = deliver_batch(
        BatchRequest.model_validate_json(json.dumps(raw)), resume=True
    )
    assert recovered.state == "complete"
    assert [op for op, _, _ in managed.calls] == ["observe", "admit"]
    # The retained admission itself keeps that explicit identity on a later resume.
    managed.calls.clear()
    assert deliver_batch(batch, resume=True).state == "complete"
    assert [op for op, _, _ in managed.calls] == ["observe", "admit"]


def test_exported_proof_after_interruption_is_verified_without_resigning(
    tmp_path, managed
):
    batch = request(tmp_path, count=1)
    repo = batch.destinations[0].push.destination.rsplit(":", 1)[0]
    managed.denied = "publish", repo
    result = deliver_batch(batch)
    assert result.outcomes[0].proof is not None
    path = Path(batch.evidence_root) / "batch.json"
    raw = json.loads(path.read_bytes())
    raw["outcomes"][0].update(
        proof=None,
        last_confirmed_stage="transferred",
        pending_operation="attest",
        state="remote_state_unconfirmed",
    )
    path.write_text(json.dumps(raw))
    managed.denied = None
    managed.calls.clear()
    assert deliver_batch(batch, resume=True).state == "complete"
    assert [op for op, _, _ in managed.calls] == [
        "observe",
        "verify",
        "publish",
        "admit",
    ]


@pytest.mark.parametrize("fault", ["transfer", "proof", "publication", "admission"])
def test_substituted_plugin_result_is_fixed_and_never_complete(
    tmp_path, managed, monkeypatch, fault
):
    batch = request(tmp_path, count=1)
    original = managed.__call__

    def changed(plugin, operation, data, **kw):
        response = original(plugin, operation, data, **kw)
        if (
            operation
            == {
                "transfer": "push",
                "proof": "attest",
                "publication": "publish",
                "admission": "admit",
            }[fault]
        ):
            key = {
                "transfer": "config_digest",
                "proof": "signer",
                "publication": "artifact_reference",
                "admission": "signer",
            }[fault]
            response.result[key] = "/private/SECRET"
        return response

    monkeypatch.setattr(operations, "run_extension", changed)
    result = deliver_batch(batch)
    assert result.state == "failed"
    assert result.outcomes[0].diagnostic == "evidence_invalid"
    assert "SECRET" not in result.model_dump_json()


def test_maximum_batch_is_bounded_and_valid(tmp_path, managed):
    result = deliver_batch(request(tmp_path, required=False, count=MAX_DESTINATIONS))
    assert result.state == "complete" and len(result.outcomes) == MAX_DESTINATIONS
