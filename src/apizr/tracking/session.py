"""Explicit, bounded observations in the caller's context; no workload execution."""

import asyncio
import os
import threading
import time
import uuid
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from types import TracebackType
from typing import Literal, TypeVar

from apizr.experiments import (
    CallParameter,
    CaptureIdentity,
    CaptureMode,
    EnvironmentEvidence,
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlanV2,
    ExperimentRunV2,
    FingerprintPolicy,
    InputArtifact,
    InputDeclaration,
    Metric,
    OutputArtifact,
    OutputDeclaration,
    Parameter,
    RunDiagnostic,
    RunTiming,
    SourceEvidence,
    SourceIdentity,
    capture_metric,
    capture_runtime_environment,
    fingerprint_input,
    fingerprint_output,
    plan_digest,
)
from apizr.experiments.model import ExperimentValue
from apizr.experiments.store import DEFAULT_STORE, RunRecordV2, prepare_store, publish
from apizr.tracking.kernel import current_cell

MAX_ITEMS = 256
MAX_CAPTURE_BYTES = 1024 * 1024
_ACTIVE: ContextVar["TrackingSession | None"] = ContextVar(
    "apizr_tracking_session", default=None
)
T = TypeVar("T", bound=ExperimentValue)


class TrackingError(ValueError):
    """Stable capture refusal, with no logged values or business exception text."""


Owner = tuple[threading.Thread, asyncio.Task[object] | None]


def _owner() -> Owner:
    try:
        task = asyncio.current_task()
    except RuntimeError:
        task = None
    return threading.current_thread(), task


def _same_owner(expected: Owner | None, observed: Owner) -> bool:
    return (
        expected is not None
        and expected[0] is observed[0]
        and expected[1] is observed[1]
    )


def capture_suppressed() -> bool:
    return (
        os.environ.get("APIZR_EXPERIMENT_RUNNER") == "1"
        or os.environ.get("APIZR_SERVED_PROCESS") == "1"
    )


class TrackingSession:
    def __init__(
        self,
        *,
        root: Path | None = None,
        store: Path | None = None,
        source: str | None = None,
        distributions: tuple[str, ...] = (),
        max_file_bytes: int = 1024**3,
        capture: CaptureIdentity | None = None,
        call_parameters: tuple[CallParameter, ...] = (),
    ):
        self.root = Path.cwd() if root is None else Path(root).absolute()
        self.store = (
            self.root / DEFAULT_STORE if store is None else Path(store).absolute()
        )
        self.source = source
        self.distributions = distributions
        self.policy = FingerprintPolicy(max_file_bytes=max_file_bytes)
        self.capture = (
            CaptureIdentity.model_validate(capture)
            if capture is not None
            else CaptureIdentity(
                mode=CaptureMode.SDK_SESSION,
                producer="apizr.tracking",
                producer_version=version("outerspace-apizr"),
            )
        )
        self._automatic_capture = capture is None
        self.call_parameters = call_parameters
        self.execution_id = uuid.uuid4().hex
        self.record: RunRecordV2 | None = None
        self.publication_error: TrackingError | None = None
        self.disabled = False
        self._entered = False
        self._closed = False
        self._context_owner: Owner | None = None
        self._token: Token[TrackingSession | None] | None = None
        self._parameters: dict[str, Parameter] = {}
        self._inputs: dict[str, InputArtifact] = {}
        self._metrics: dict[str, Metric] = {}
        self._outputs: dict[str, OutputArtifact] = {}
        self._bytes = 0
        self._failure: str | None = None
        self._plan: ExperimentPlanV2 | None = None
        self._environment: EnvironmentEvidence | None = None
        self._started_at: datetime | None = None
        self._started_clock = 0.0

    def __enter__(self) -> "TrackingSession":
        if self._entered or self._closed:
            raise TrackingError("tracking_session_reused")
        self._context_owner = _owner()
        self.disabled = capture_suppressed()
        active = _ACTIVE.get()
        if (
            not self.disabled
            and active is not None
            and _same_owner(active._context_owner, self._context_owner)
        ):
            active._failure = "tracking_nested_session"
            raise TrackingError("tracking_nested_session")
        if not self.disabled:
            if self.capture.cell.origin == EvidenceOrigin.UNKNOWN:
                try:
                    cell = current_cell()
                except Exception:
                    raise TrackingError("tracking_kernel_observation_invalid") from None
                if cell.origin == EvidenceOrigin.RUNTIME:
                    self.capture = CaptureIdentity.model_validate(
                        self.capture.model_copy(
                            update={
                                "cell": cell,
                                "mode": CaptureMode.JUPYTER_CELL
                                if self._automatic_capture
                                else self.capture.mode,
                            }
                        )
                    )
            prepare_store(self.store)
            self._environment = capture_runtime_environment(
                distributions=self.distributions, root=self.root, policy=self.policy
            ).evidence
            subject = SourceEvidence()
            if self.source is not None:
                selection = InputDeclaration(name="source", reference=self.source)
                observed = fingerprint_input(self.root, selection, policy=self.policy)
                artifact = observed.artifacts[0]
                if observed.diagnostics or artifact.digest is None:
                    raise TrackingError("tracking_source_unavailable")
                suffix = Path(self.source).suffix
                if suffix not in {".py", ".ipynb"}:
                    raise TrackingError("tracking_source_kind")
                subject = SourceEvidence(
                    identity=SourceIdentity(
                        kind="python" if suffix == ".py" else "notebook",
                        reference=self.source,
                        digest=artifact.digest,
                    ),
                    origin=EvidenceOrigin.RUNTIME,
                )
            self._plan = ExperimentPlanV2(
                subject=subject,
                execution=ExecutionIntent(kind="in-process"),
                capture=self.capture,
            )
            # Validate selected call evidence before business code starts.
            ExperimentRunV2(
                plan_digest=plan_digest(self._plan),
                subject=subject,
                capture=self.capture,
                execution_id=self.execution_id,
                call_parameters=self.call_parameters,
                status="success",
            )
            self._bytes = sum(
                len(item.model_dump_json().encode("utf-8"))
                for item in self.call_parameters
            )
            if self._bytes > MAX_CAPTURE_BYTES:
                raise TrackingError("tracking_capture_limit")
        self._started_at = datetime.now(UTC)
        self._started_clock = time.monotonic()
        self._entered = True
        self._token = _ACTIVE.set(self)
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        if not _same_owner(self._context_owner, _owner()):
            raise TrackingError("tracking_context_mismatch")
        try:
            if not self._closed:
                self._finish(
                    "success"
                    if error is None
                    else "cancelled"
                    if isinstance(error, (KeyboardInterrupt, asyncio.CancelledError))
                    else "failed"
                )
        except BaseException:
            self.publication_error = TrackingError("tracking_publication_failed")
            if error is None:
                raise
            BaseException.add_note(
                error,
                "Apizr capture could not be published (tracking_publication_failed).",
            )
        finally:
            if self._token is not None:
                _ACTIVE.reset(self._token)
                self._token = None
        return False

    def _open(self) -> None:
        if not self._entered:
            raise TrackingError("tracking_session_not_started")
        if not _same_owner(self._context_owner, _owner()):
            raise TrackingError("tracking_context_mismatch")
        if self._closed:
            raise TrackingError("tracking_session_closed")

    @classmethod
    def current(cls) -> "TrackingSession | None":
        """The active session only when the caller owns its execution context."""
        active = _ACTIVE.get()
        return (
            active
            if active is not None and _same_owner(active._context_owner, _owner())
            else None
        )

    def _reserve(self, items: dict[str, T], name: str) -> None:
        self._open()
        if type(name) is not str:
            self._failure = "tracking_name_invalid"
            raise TrackingError(self._failure)
        if name in items:
            self._failure = "tracking_duplicate_key"
            raise TrackingError(self._failure)
        if len(items) >= MAX_ITEMS:
            self._failure = "tracking_count_limit"
            raise TrackingError(self._failure)

    def _append(self, items: dict[str, T], item: T, name: str) -> None:
        size = len(item.model_dump_json().encode("utf-8"))
        if self._bytes + size > MAX_CAPTURE_BYTES:
            self._failure = "tracking_capture_limit"
            raise TrackingError(self._failure)
        self._bytes += size
        items[name] = item

    def log_parameter(self, name: str, value: object) -> None:
        self._reserve(self._parameters, name)
        if self.disabled:
            return
        try:
            item = Parameter.model_validate(
                {"name": name, "value": value, "origin": EvidenceOrigin.RUNTIME}
            )
        except (ValueError, UnicodeError):
            self._failure = "tracking_parameter_invalid"
            raise TrackingError(self._failure) from None
        self._append(self._parameters, item, name)

    def log_metric(self, name: str, value: object, *, unit: str | None = None) -> None:
        self._reserve(self._metrics, name)
        if self.disabled:
            return
        try:
            item = capture_metric(name, value, unit=unit)
        except ValueError:
            self._failure = "tracking_metric_invalid"
            raise TrackingError(self._failure) from None
        self._append(self._metrics, item, name)

    def log_input(
        self, name: str, reference: str | None = None, *, uri: str | None = None
    ) -> None:
        self._reserve(self._inputs, name)
        if self.disabled:
            return
        try:
            if reference is None and uri is None:
                item = InputArtifact(name=name, origin=EvidenceOrigin.UNKNOWN)
            else:
                selection = InputDeclaration(name=name, reference=reference, uri=uri)
                result = fingerprint_input(self.root, selection, policy=self.policy)
                artifact = result.artifacts[0]
                if result.diagnostics and uri is None:
                    raise ValueError("input_unavailable")
                item = InputArtifact.model_validate(
                    artifact.model_copy(
                        update={
                            "origin": EvidenceOrigin.RUNTIME,
                            "content_origin": EvidenceOrigin.RUNTIME
                            if artifact.digest
                            else EvidenceOrigin.UNKNOWN,
                        }
                    )
                )
        except (ValueError, UnicodeError, OSError):
            self._failure = "tracking_input_invalid"
            raise TrackingError(self._failure) from None
        self._append(self._inputs, item, name)

    def log_artifact(
        self, name: str, reference: str, *, media_type: str | None = None
    ) -> None:
        self._reserve(self._outputs, name)
        if self.disabled:
            return
        try:
            result = fingerprint_output(
                self.root,
                OutputDeclaration(
                    name=name, reference=reference, media_type=media_type
                ),
                policy=self.policy,
            )
            if result.diagnostics or not result.artifacts:
                raise ValueError("output_unavailable")
            item = result.artifacts[0]
        except (ValueError, UnicodeError, OSError):
            self._failure = "tracking_artifact_invalid"
            raise TrackingError(self._failure) from None
        self._append(self._outputs, item, name)

    def finalize(self) -> RunRecordV2 | None:
        if self._closed and (self.record is not None or self.disabled):
            if not _same_owner(self._context_owner, _owner()):
                raise TrackingError("tracking_context_mismatch")
            return self.record
        return self._finish("success")

    def _finish(self, status: str) -> RunRecordV2 | None:
        self._open()
        self._closed = True
        if self.disabled:
            return None
        assert self._plan is not None and self._environment is not None
        diagnostic = self._failure or (
            "tracking_cancelled"
            if status == "cancelled"
            else "tracking_workload_failed"
            if status == "failed"
            else None
        )
        actual_status = "failed" if self._failure else status
        run = ExperimentRunV2.model_validate(
            {
                "plan_digest": plan_digest(self._plan),
                "subject": self._plan.subject,
                "capture": self.capture,
                "execution_id": self.execution_id,
                "call_parameters": self.call_parameters,
                "status": actual_status,
                "observed_inputs": tuple(self._inputs.values()),
                "effective_parameters": tuple(self._parameters.values()),
                "environment": self._environment,
                "metrics": tuple(self._metrics.values()),
                "outputs": tuple(self._outputs.values()),
                "timing": RunTiming(
                    started_at=self._started_at,
                    ended_at=datetime.now(UTC),
                    duration_seconds=max(0.0, time.monotonic() - self._started_clock),
                    origin=EvidenceOrigin.RUNTIME,
                ),
                "diagnostics": (
                    RunDiagnostic(code=diagnostic, origin=EvidenceOrigin.RUNTIME),
                )
                if diagnostic
                else (),
            }
        )
        try:
            self.record = publish(self.store, self._plan, run)
        except BaseException:
            self.publication_error = TrackingError("tracking_publication_failed")
            raise
        return self.record


def session(
    *,
    root: Path | None = None,
    store: Path | None = None,
    source: str | None = None,
    distributions: tuple[str, ...] = (),
    max_file_bytes: int = 1024**3,
    capture: CaptureIdentity | None = None,
    call_parameters: tuple[CallParameter, ...] = (),
) -> TrackingSession:
    return TrackingSession(
        root=root,
        store=store,
        source=source,
        distributions=distributions,
        max_file_bytes=max_file_bytes,
        capture=capture,
        call_parameters=call_parameters,
    )


def active_session() -> TrackingSession | None:
    """Return only the session owned by this thread/task, never an inherited one."""
    return TrackingSession.current()


def _current() -> TrackingSession:
    active = active_session()
    if active is None:
        raise TrackingError("tracking_no_active_session")
    return active


def log_parameter(name: str, value: object) -> None:
    if not capture_suppressed():
        _current().log_parameter(name, value)


def log_metric(name: str, value: object, *, unit: str | None = None) -> None:
    if not capture_suppressed():
        _current().log_metric(name, value, unit=unit)


def log_input(
    name: str, reference: str | None = None, *, uri: str | None = None
) -> None:
    if not capture_suppressed():
        _current().log_input(name, reference, uri=uri)


def log_artifact(name: str, reference: str, *, media_type: str | None = None) -> None:
    if not capture_suppressed():
        _current().log_artifact(name, reference, media_type=media_type)
