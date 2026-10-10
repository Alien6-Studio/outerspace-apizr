"""Bounded trusted local workload supervision and factual boundary observations."""

import base64
import os
import selectors
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from apizr.contracts.json import encode
from apizr.execution.protocol import frame, size
from apizr.execution.supervisor import kill_group
from apizr.experiments.bindings import automatic_metrics
from apizr.experiments.inputs import (
    FingerprintPolicy,
    InputDeclaration,
    fingerprint_inputs,
)
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.model import (
    EnvironmentEvidence,
    EvidenceOrigin,
    ExperimentPlan,
    ExperimentRun,
    InputArtifact,
    OutputArtifact,
    RunDiagnostic,
    RunTiming,
)
from apizr.experiments.notebook_source import code_cells
from apizr.experiments.outputs import OutputDeclaration, fingerprint_outputs
from apizr.experiments.planning import RunOptions, derive_plan
from apizr.experiments.run_protocol import (
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    WorkerFinished,
    WorkerStarted,
    WorkloadRequest,
)
from apizr.experiments.serialization import plan_digest, validate_run_binding
from apizr.experiments.store import DEFAULT_STORE, RunRecord, prepare_store, publish
from apizr.workspace.files import absolute_path, directory_fd, read_regular


@dataclass(frozen=True)
class _Outcome:
    status: Literal["success", "failed", "cancelled"]
    diagnostic: str | None = None
    environment: EnvironmentEvidence | None = None
    observation: WorkerFinished | None = None


def _exchange(request: WorkloadRequest, root: Path, options: RunOptions) -> _Outcome:
    payload = frame(encode(request.model_dump(mode="json"), MAX_REQUEST_BYTES))
    deadline = time.monotonic() + options.timeout_ms / 1000
    environment = (
        dict(os.environ)
        if options.inherit_environment
        else {n: os.environ[n] for n in options.environment_names if n in os.environ}
    )
    observed: EnvironmentEvidence | None = None
    finished: WorkerFinished | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-m", "apizr.experiments.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=root,
            env=environment,
            start_new_session=True,
            close_fds=True,
            bufsize=0,
        )
    except OSError:
        return _Outcome("failed", "worker_failed")
    sent = received = 0
    buffer = bytearray()
    try:
        assert process.stdin is not None and process.stdout is not None
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdin.fileno(), False)
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdin, selectors.EVENT_WRITE)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return _Outcome("failed", "execution_timeout", observed)
                for key, events in selector.select(min(remaining, 0.05)):
                    if events & selectors.EVENT_WRITE:
                        sent += os.write(key.fd, payload[sent : sent + 65536])
                        if sent == len(payload):
                            selector.unregister(key.fileobj)
                            process.stdin.close()
                    else:
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            process.stdout.close()
                        buffer.extend(chunk)
                        received += len(chunk)
                        if received > 2 * (MAX_RESPONSE_BYTES + 8):
                            raise ValueError("worker_protocol")
                        while len(buffer) >= 8:
                            length = size(bytes(buffer[:8]), MAX_RESPONSE_BYTES)
                            if len(buffer) < length + 8:
                                break
                            raw = bytes(buffer[8 : length + 8])
                            del buffer[: length + 8]
                            if observed is None:
                                observed = WorkerStarted.model_validate_json(
                                    raw
                                ).environment
                            elif finished is None:
                                finished = WorkerFinished.model_validate_json(raw)
                            else:
                                raise ValueError("worker_protocol")
                if process.poll() is not None:
                    # Same proven cleanup as capability execution; includes
                    # ordinary descendants which retained inherited pipe handles.
                    kill_group(process)
            code = process.wait(timeout=max(0, deadline - time.monotonic()))
        if code or buffer or finished is None:
            return _Outcome("failed", "worker_failed", observed)
        if not {p.name for p in finished.parameters} <= set(request.parameters) or not {
            m.name for m in finished.metrics
        } <= {m.name for m in (*request.automatic_metrics, *request.required_metrics)}:
            raise ValueError("worker_protocol")
        return _Outcome(finished.status, finished.diagnostic, observed, finished)
    except KeyboardInterrupt:
        return _Outcome("cancelled", "execution_cancelled", observed)
    except subprocess.TimeoutExpired:
        return _Outcome("failed", "execution_timeout", observed)
    except (OSError, ValueError, RecursionError):
        return _Outcome("failed", "worker_failed", observed)
    finally:
        try:
            kill_group(process)
        finally:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            finally:
                if process.stdout is not None:
                    process.stdout.close()


def _source(
    inspection: ExperimentInspection, plan: ExperimentPlan, root: Path
) -> tuple[bytes, bytes, str | bytes]:
    try:
        raw = read_regular(root / plan.subject.reference, 16 * 1024**2)
        if sha256(raw).hexdigest() != plan.subject.digest:
            raise ValueError
        executable = raw
        signals: str | bytes = raw
        if plan.subject.kind == "notebook":
            from apizr.generators.notebooks import inspect_notebook_bytes

            signals = code_cells(raw).source
            assert plan.subject.module is not None
            converted = inspect_notebook_bytes(raw, module_name=plan.subject.module)
            executable = converted.python_source.encode("utf-8")
        signal_bytes = signals.encode("utf-8") if isinstance(signals, str) else signals
        if (
            sha256(executable).hexdigest() != plan.subject.executable_digest
            or sha256(signal_bytes).hexdigest() != inspection.code.signal_digest.value
        ):
            raise ValueError
        return raw, executable, signals
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        raise ValueError("source_changed") from None


def _output_selection(
    inspection: ExperimentInspection, options: RunOptions
) -> tuple[OutputDeclaration, ...]:
    automatic: dict[str, set[OutputDeclaration]] = {}
    for signal in inspection.outputs.signals:
        d = signal.declaration
        automatic.setdefault(d.name, set()).add(d)
    required = {d.name: d for d in options.outputs}
    selected = {
        name: next(iter(items))
        for name, items in automatic.items()
        if len(items) == 1 and name not in required
    }
    # Bounds include the union, never silently truncate explicit selections.
    selected.update(required)
    if len(selected) > 256:
        raise ValueError("output_selection_limit")
    return tuple(selected[name] for name in sorted(selected))


def execute_plan(
    inspection: ExperimentInspection,
    plan: ExperimentPlan,
    *,
    root: Path,
    options: RunOptions | None = None,
) -> ExperimentRun:
    """Execute once after exact preflight; no persistence and no automatic retry.

    The caller persists every returned status. Admission/source/input failures
    raise before worker launch. Environment facts come only from a started worker.
    """
    inspection = ExperimentInspection.model_validate(inspection)
    plan = ExperimentPlan.model_validate(plan)
    options = RunOptions() if options is None else RunOptions.model_validate(options)
    if os.name != "posix":
        raise ValueError("runner_requires_posix")
    if plan_digest(plan) != plan_digest(derive_plan(inspection, execution=options)):
        raise ValueError("plan_mismatch")
    root = absolute_path(root)
    with directory_fd(root):
        pass
    original, executable, signals = _source(inspection, plan, root)
    selections = _output_selection(inspection, options)
    policy = inspection.fingerprint_policy
    before = fingerprint_inputs(root, plan.inputs, policy=policy).artifacts
    if any(
        (p.digest is not None and p.digest != b.digest)
        or (p.size is not None and p.size != b.size)
        for p, b in zip(plan.inputs, before, strict=True)
    ):
        raise ValueError("input_changed")
    request = WorkloadRequest(
        subject=plan.subject,
        plan_digest=plan_digest(plan),
        original=base64.b64encode(original).decode("ascii"),
        executable=base64.b64encode(executable).decode("ascii"),
        parameters=tuple(p.name for p in plan.parameters),
        automatic_metrics=automatic_metrics(signals, inspection.metrics),
        required_metrics=options.metrics,
        distributions=tuple(
            sorted(
                set(
                    inspection.randomness.relevant_distributions
                    + inspection.metrics.relevant_distributions
                    + inspection.outputs.relevant_distributions
                )
            )
        ),
        inputs=plan.inputs,
        fingerprint_policy=policy,
    )
    started = datetime.now(UTC)
    monotonic_start = time.monotonic()
    try:
        outcome = _exchange(request, root, options)
    except OSError:
        # A cleanup error must not erase the fact that execution was attempted.
        outcome = _Outcome("failed", "worker_cleanup_failed")
    ended = datetime.now(UTC)
    duration = max(0.0, time.monotonic() - monotonic_start)
    diagnostics: set[str] = {outcome.diagnostic} if outcome.diagnostic else set()
    observed: list[InputArtifact] = []
    outputs: tuple[OutputArtifact, ...] = ()
    cancelled = outcome.status == "cancelled"
    try:
        after = fingerprint_inputs(root, plan.inputs, policy=policy).artifacts
        for first, last in zip(before, after, strict=True):
            if (first.digest, first.size) != (last.digest, last.size):
                diagnostics.add("input_changed_during_execution")
                continue
            observed.append(
                last.model_copy(
                    update={
                        "origin": EvidenceOrigin.RUNTIME
                        if last.digest
                        else EvidenceOrigin.UNKNOWN,
                        "content_origin": EvidenceOrigin.RUNTIME
                        if last.digest
                        else EvidenceOrigin.UNKNOWN,
                    }
                )
            )
        if outcome.status == "success" and not diagnostics:
            result = fingerprint_outputs(
                root,
                selections,
                policy=FingerprintPolicy(max_file_bytes=options.max_output_bytes),
            )
            if {d.name for d in options.outputs} - {a.name for a in result.artifacts}:
                diagnostics.add("output_capture_failed")
            else:
                outputs = result.artifacts
    except KeyboardInterrupt:
        cancelled = True
        diagnostics.add("execution_cancelled")
    except (OSError, ValueError, UnicodeError, RecursionError):
        diagnostics.add("observation_failed")
    if ended < started:
        diagnostics.add("clock_reversed")
    status = "cancelled" if cancelled else outcome.status
    if status == "success" and diagnostics:
        status = "failed"
    observation = outcome.observation if outcome.status == "success" else None
    run = ExperimentRun(
        plan_digest=plan_digest(plan),
        subject=plan.subject,
        status=status,
        observed_inputs=tuple(observed),
        effective_parameters=observation.parameters if observation else (),
        randomness=(),
        environment=outcome.environment,
        metrics=observation.metrics if observation else (),
        outputs=outputs,
        timing=RunTiming(
            started_at=started,
            ended_at=ended if ended >= started else None,
            duration_seconds=duration,
            origin=EvidenceOrigin.RUNTIME,
        ),
        diagnostics=tuple(
            RunDiagnostic(code=code, origin=EvidenceOrigin.RUNTIME)
            for code in sorted(diagnostics)
        ),
    )
    validate_run_binding(run, plan)
    return run


def run_experiment(
    source: Path,
    *,
    root: Path | None = None,
    module_name: str | None = None,
    declarations: tuple[InputDeclaration, ...] = (),
    fingerprint_policy: FingerprintPolicy | None = None,
    options: RunOptions | None = None,
    store: Path | None = None,
) -> RunRecord:
    """Inspect, derive, execute once and durably record trusted local evidence."""
    source = absolute_path(source)
    root = absolute_path(root) if root is not None else source.parent
    policy = (
        fingerprint_policy if fingerprint_policy is not None else FingerprintPolicy()
    )
    inspection = inspect_experiment(
        source,
        root=root,
        module_name=module_name,
        declarations=declarations,
        fingerprint_policy=policy,
    )
    plan = derive_plan(inspection, execution=options)
    destination = store if store is not None else root / DEFAULT_STORE
    # Refuse an unusable/corrupt history before executing a workload with effects.
    prepare_store(destination)
    run = execute_plan(inspection, plan, root=root, options=options)
    return publish(destination, plan, run)
