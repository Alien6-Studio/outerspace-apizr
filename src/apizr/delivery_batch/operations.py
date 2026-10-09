"""Sequential managed delivery: independent effects, explicit retained progress."""

import os
import time
from pathlib import Path
from threading import Event
from typing import Any, TypeVar

from pydantic import BaseModel

from apizr.contracts.delivery import identity
from apizr.contracts.publication import (
    AdmitRequest,
    AttestRequest,
    ObserveRequest,
    PublishRequest,
)
from apizr.contracts.results import (
    AdmissionResult,
    DeliveryResult,
    ObservationResult,
    PublishResult,
    PushResult,
)
from apizr.extension_runtime import (
    CleanupFailed,
    ExtensionError,
    InvocationCancelled,
    Limits,
)
from apizr.plugins.local import PluginError, run_extension
from apizr.plugins.local.control import InstallationCancelled, InstallControl
from apizr.plugins.local.store import installation_lock, private_directory
from apizr.workspace.operator_policy import AuthorizationDenied, OperatorPolicy

from . import evidence
from .models import (
    BatchRequest,
    BatchResult,
    Destination,
    DestinationOutcome,
    Diagnostic,
    Operation,
)

T = TypeVar("T", bound=BaseModel)
OCI = "outerspace-apizr-oci"
ATTEST = "outerspace-apizr-attest"


class BatchError(Exception):
    """Shared input/evidence refusal; a later local write can follow remote effects."""


def _aggregate(
    request: BatchRequest, outcomes: list[DestinationOutcome], cancelled=False
) -> BatchResult:
    build = request.build
    assert build.delivery_manifest is not None and build.delivery_plan is not None
    count = sum(o.state == "complete" for o in outcomes)
    return BatchResult.model_validate_json(
        BatchResult(
            build=build.delivery_manifest,
            delivery_manifest_digest=identity(build.delivery_manifest),
            proof_requirement=build.delivery_plan.proof_requirement,
            state="cancelled"
            if cancelled
            else "complete"
            if count == len(outcomes)
            else "partial"
            if count
            else "failed",
            outcomes=tuple(outcomes),
        ).model_dump_json(by_alias=True)
    )


def _initial(request: BatchRequest) -> BatchResult:
    return _aggregate(
        request,
        [
            DestinationOutcome(destination=d.push.destination)
            for d in request.destinations
        ],
    )


def _retained(initial: BatchResult, saved: Path) -> BatchResult:
    previous = BatchResult.model_validate_json(evidence.read(saved), strict=True)
    if (
        previous.build,
        previous.delivery_manifest_digest,
        previous.proof_requirement,
        tuple(o.destination for o in previous.outcomes),
    ) != (
        initial.build,
        initial.delivery_manifest_digest,
        initial.proof_requirement,
        tuple(o.destination for o in initial.outcomes),
    ):
        raise evidence.EvidenceError()
    return previous


def inspect_batch(request: BatchRequest) -> BatchResult:
    """Inspect retained local evidence only; never create, lock, invoke or observe.

    The existing aggregate contract represents an unstarted batch as ``failed``
    with every outcome ``not_started`` and no diagnostic or pending operation.
    """
    try:
        request = BatchRequest.model_validate_json(
            request.model_dump_json(by_alias=True), strict=True
        )
        root = Path(request.evidence_root)
        if root.resolve() != root.absolute():
            raise evidence.EvidenceError()
        initial = _initial(request)
        try:
            return _retained(initial, root / "batch.json")
        except FileNotFoundError:
            return initial
    except (evidence.EvidenceError, ValueError, TypeError, OSError, PluginError):
        raise BatchError("batch_evidence_or_request_invalid") from None


class Coordinator:
    def __init__(
        self,
        request: BatchRequest,
        root: Path,
        outcomes: list[DestinationOutcome],
        directory: Path | None,
        policy: OperatorPolicy | None,
        cancel: Event,
    ):
        self.request, self.root, self.outcomes = request, root, outcomes
        self.directory, self.policy, self.cancel = directory, policy, cancel
        self.index = 0
        self.operation: Operation = "observe"
        self.started = False

    @property
    def outcome(self) -> DestinationOutcome:
        return self.outcomes[self.index]

    def save(self, **changes) -> None:
        candidate = DestinationOutcome.model_validate(
            self.outcome.model_copy(update=changes).model_dump(by_alias=True)
        )
        pending = list(self.outcomes)
        pending[self.index] = candidate
        result = _aggregate(self.request, pending)
        evidence.checkpoint(self.root, result)
        self.outcomes[self.index] = candidate

    def call(
        self,
        plugin: str,
        operation: Operation,
        arguments: BaseModel,
        result: type[T],
        timeout: int,
    ) -> T:
        if self.cancel.is_set():
            raise InvocationCancelled()
        self.operation = operation
        self.started = False
        before = self.outcome
        if operation in {"push", "attest", "publish", "admit"}:
            self.save(
                state="remote_state_unconfirmed",
                diagnostic="remote_state_unconfirmed",
                pending_operation=operation,
            )
        try:
            self.started = True
            response = run_extension(
                plugin,
                operation,
                arguments.model_dump(mode="json", by_alias=True),
                directory=self.directory,
                operator_policy=self.policy,
                cancel=self.cancel,
                limits=Limits(wall_time_ms=timeout),
            )
        except AuthorizationDenied:
            # The managed admission guarantees refusal before any plugin effect.
            self.outcomes[self.index] = before
            self.started = False
            raise
        return result.model_validate(response.result)

    def refuse(self, diagnostic: Diagnostic, *, uncertain=False) -> None:
        self.save(
            state="remote_state_unconfirmed" if uncertain else "failed",
            diagnostic=diagnostic,
        )

    def deliver(self, destination: Destination) -> None:
        push = destination.push
        assert push.delivery_manifest is not None and push.delivery_plan is not None
        out = self.outcome
        was_complete = out.state == "complete" or out.last_confirmed_stage in {
            "admitted",
            "complete",
        }
        child = evidence.directory(self.root, push.destination)
        push_path = child / "push.json"
        proof_path = child / "proof"
        reference = (
            out.transfer.digest_reference
            if out.transfer
            else destination.recovery_reference
        )
        if (
            out.transfer is not None
            or out.pending_operation == "push"
            or destination.recovery_reference is not None
        ):
            observation = self.call(
                OCI,
                "observe",
                ObserveRequest(
                    schema="apizr.observe-delivery/v1",
                    push=push,
                    expected_reference=reference,
                ),
                ObservationResult,
                push.timeout_ms,
            )
            if observation.destination != push.destination:
                raise evidence.EvidenceError()
            if observation.state == "conflict":
                self.refuse("destination_conflict")
                return
            if observation.state == "remote_state_unconfirmed":
                self.refuse("remote_state_unconfirmed", uncertain=True)
                return
            if (
                was_complete or (out.transfer is not None and destination.proof is None)
            ) and observation.state != "verified":
                self.refuse("destination_absent")
                return
            if observation.image is None:
                self.refuse("transfer_identity_required", uncertain=True)
                return
            image = observation.image
            if out.transfer is not None:
                if (
                    image.digest_reference,
                    image.config_digest,
                    image.manifest_digest,
                ) != (
                    out.transfer.digest_reference,
                    out.transfer.config_digest,
                    out.transfer.manifest_digest,
                ):
                    raise evidence.EvidenceError()
            else:
                if (
                    push.delivery_plan.proof_requirement == "optional"
                    and observation.state != "verified"
                ):
                    recovered = push.model_copy(
                        update={"resume_reference": image.digest_reference}
                    )
                    transfer = self.call(
                        OCI, "push", recovered, PushResult, push.timeout_ms
                    )
                else:
                    transfer = PushResult(
                        destination=push.destination,
                        digest_reference=image.digest_reference,
                        platform=push.platform,
                        image_id=push.image_id,
                        config_digest=image.config_digest,
                        manifest_digest=image.manifest_digest,
                        inputs_sha256=push.inputs_sha256,
                        delivery_plan_digest=push.delivery_manifest.delivery_plan_digest,
                        delivery_manifest_digest=identity(push.delivery_manifest),
                        proof_requirement=push.delivery_plan.proof_requirement,
                        transfer_verified=True,
                        destination_promoted=push.delivery_plan.proof_requirement
                        == "optional",
                        delivery_admitted=False,
                    )
                self.save(
                    transfer=transfer,
                    last_confirmed_stage="transferred",
                    state="failed",
                    diagnostic=None,
                    pending_operation=None,
                )
        else:
            transfer = self.call(OCI, "push", push, PushResult, push.timeout_ms)
            self.save(
                transfer=transfer,
                last_confirmed_stage="transferred",
                state="failed",
                diagnostic=None,
                pending_operation=None,
            )
        transfer = self.outcome.transfer
        assert transfer is not None
        evidence.write_once(push_path, transfer)
        if destination.proof is None:
            self.save(
                state="complete",
                last_confirmed_stage="complete",
                diagnostic=None,
                pending_operation=None,
            )
            return
        proof = destination.proof
        timeout = proof.verification.timeout_ms
        common: dict[str, Any] = proof.verification.model_dump() | {
            "expected_reference": transfer.digest_reference
        }
        if (
            self.outcome.publication is None
            and self.outcome.admission is None
            and destination.selected_artifact is None
        ):
            if os.path.lexists(proof_path):
                # Retained proof must be independently verified, never signed again.
                from apizr.contracts.publication import VerifyRequest

                verified = self.call(
                    ATTEST,
                    "verify",
                    VerifyRequest(
                        schema="apizr.verify-delivery/v1",
                        proof_dir=str(proof_path),
                        **common,
                    ),
                    DeliveryResult,
                    timeout,
                )
                if self.outcome.proof is not None and verified != self.outcome.proof:
                    raise evidence.EvidenceError()
            else:
                if self.outcome.proof is not None:
                    raise evidence.EvidenceError()
                verified = self.call(
                    ATTEST,
                    "attest",
                    AttestRequest(
                        schema="apizr.attest-delivery/v1",
                        build_result=str(self.root / "build.json"),
                        push_result=str(push_path),
                        docker=push.docker,
                        authentication=push.authentication,
                        output_dir=str(proof_path),
                        **proof.signing.model_dump(),
                        **common,
                    ),
                    DeliveryResult,
                    timeout,
                )
            if (
                verified.signer != proof.verification.expected_signer
                or verified.attest_tool is None
                or verified.attest_tool.model_dump()
                != proof.verification.tool.model_dump(include={"version", "sha256"})
            ):
                raise evidence.EvidenceError()
            pending = self.outcome.pending_operation
            self.save(
                proof=verified,
                last_confirmed_stage="proof_created",
                state="failed",
                diagnostic=None,
                pending_operation=pending if pending == "publish" else None,
            )
        publication = self.outcome.publication
        artifact = destination.selected_artifact
        if self.outcome.admission is not None:
            retained_artifact = self.outcome.admission.proof_artifact_reference
            if artifact is not None and artifact != retained_artifact:
                raise evidence.EvidenceError()
            artifact = retained_artifact
        if publication is not None and publication.state == "verified":
            if artifact is not None and artifact != publication.artifact_reference:
                raise evidence.EvidenceError()
            artifact = publication.artifact_reference
        if artifact is None and (
            self.outcome.pending_operation == "publish"
            or (
                publication is not None
                and publication.state == "remote_state_unconfirmed"
            )
        ):
            self.refuse("proof_selection_required", uncertain=True)
            return
        if artifact is None:
            publication = self.call(
                ATTEST,
                "publish",
                PublishRequest(
                    schema="apizr.publish-proof/v1",
                    proof_dir=str(proof_path),
                    transport=proof.transport,
                    **common,
                ),
                PublishResult,
                timeout,
            )
            if publication.state != "verified":
                self.save(
                    publication=publication,
                    state="remote_state_unconfirmed",
                    diagnostic="proof_selection_required",
                    pending_operation="publish",
                )
                return
            self.save(
                publication=publication,
                last_confirmed_stage="proof_published",
                state="failed",
                diagnostic=None,
                pending_operation=None,
            )
            artifact = publication.artifact_reference
        assert artifact is not None
        admission = self.call(
            ATTEST,
            "admit",
            AdmitRequest(
                schema="apizr.admit-delivery/v1",
                push_result=str(push_path),
                delivery_manifest=push.delivery_manifest,
                destination=push.destination,
                artifact_reference=artifact,
                transport=proof.transport,
                docker=push.docker,
                **common,
            ),
            AdmissionResult,
            timeout,
        )
        if (
            admission.proof_artifact_reference != artifact
            or admission.signer != proof.verification.expected_signer
        ):
            raise evidence.EvidenceError()
        if admission.state != "admitted":
            self.save(
                admission=admission,
                state="remote_state_unconfirmed",
                diagnostic="remote_state_unconfirmed",
                pending_operation="admit",
            )
            return
        self.save(
            admission=admission,
            last_confirmed_stage="admitted",
            state="complete",
            diagnostic=None,
            pending_operation=None,
        )


def deliver_batch(
    request: BatchRequest,
    *,
    resume: bool = False,
    directory: Path | None = None,
    operator_policy: OperatorPolicy | None = None,
    cancel: Event | None = None,
) -> BatchResult:
    """Deliver an existing build; every effect uses managed per-repository admission."""
    try:
        request = BatchRequest.model_validate_json(
            request.model_dump_json(by_alias=True)
        )
        root = Path(request.evidence_root)
        # Refuse symlinked roots; child names are bounded hashes, never destinations.
        if root.resolve() != root.absolute():
            raise evidence.EvidenceError()
        private_directory(root)
        cancellation = cancel or Event()
        with installation_lock(
            root, control=InstallControl(time.monotonic() + 30, cancellation)
        ):
            initial = _initial(request)
            outcomes = list(initial.outcomes)
            saved = root / "batch.json"
            if os.path.lexists(saved):
                if not resume:
                    raise evidence.EvidenceError()
                previous = _retained(initial, saved)
                outcomes = list(previous.outcomes)
            elif resume:
                raise evidence.EvidenceError()
            evidence.write_once(root / "build.json", request.build)
            evidence.checkpoint(root, _aggregate(request, outcomes))
            runner = Coordinator(
                request, root, outcomes, directory, operator_policy, cancellation
            )
            for index, destination in enumerate(request.destinations):
                runner.index = index
                if runner.cancel.is_set():
                    break
                try:
                    runner.deliver(destination)
                except AuthorizationDenied:
                    runner.refuse("authorization_refused")
                except CleanupFailed:
                    # An unaccounted native child is fatal, never a reason to
                    # advance to another destination or accept another tool call.
                    runner.cancel.set()
                    try:
                        runner.refuse("cancelled", uncertain=runner.started)
                        evidence.checkpoint(root, _aggregate(request, outcomes, True))
                    finally:
                        raise CleanupFailed() from None
                except (InvocationCancelled, KeyboardInterrupt):
                    runner.cancel.set()
                    runner.refuse(
                        "cancelled",
                        uncertain=runner.started
                        and runner.operation in {"push", "publish", "admit"},
                    )
                    break
                except (evidence.EvidenceError, ValueError, TypeError):
                    runner.refuse(
                        "evidence_invalid",
                        uncertain=runner.outcome.pending_operation
                        in {"push", "publish", "admit"},
                    )
                except (ExtensionError, PluginError, OSError):
                    diagnostics: dict[Operation, Diagnostic] = {
                        "push": "transfer_failed",
                        "attest": "attestation_failed",
                        "publish": "proof_publication_failed",
                        "admit": "admission_failed",
                        "observe": "remote_state_unconfirmed",
                        "verify": "evidence_invalid",
                    }
                    runner.refuse(
                        diagnostics[runner.operation],
                        uncertain=runner.started
                        and runner.operation in {"push", "publish", "admit", "observe"},
                    )
            result = _aggregate(request, outcomes, runner.cancel.is_set())
            evidence.checkpoint(root, result)
            return result
    except InstallationCancelled:
        return _aggregate(request, list(inspect_batch(request).outcomes), True)
    except (evidence.EvidenceError, ValueError, TypeError, OSError, PluginError):
        raise BatchError("batch_evidence_or_request_invalid") from None
