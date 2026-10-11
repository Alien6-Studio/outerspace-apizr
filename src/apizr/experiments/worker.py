"""Explicit trusted experiment execution. Host access, never a security sandbox."""

import os
import sys
import types
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

from apizr.contracts.json import encode
from apizr.execution.protocol import frame, read_frame
from apizr.experiments.environment import capture_runtime_environment
from apizr.experiments.inputs import fingerprint_inputs
from apizr.experiments.metrics import capture_metric
from apizr.experiments.model import EvidenceOrigin, Metric, Parameter
from apizr.experiments.run_protocol import (
    MAX_CAPTURE_BYTES,
    MAX_REQUEST_BYTES,
    MAX_RESPONSE_BYTES,
    WorkerFinished,
    WorkerStarted,
    WorkloadRequest,
)
from apizr.workspace.files import read_regular


def observe(request: WorkloadRequest, namespace: dict[str, object]) -> WorkerFinished:
    parameters: list[Parameter] = []
    metrics: dict[str, Metric] = {}
    used = 0

    def admits(value: Parameter | Metric) -> bool:
        nonlocal used
        amount = len(encode(value.model_dump(mode="json"), MAX_CAPTURE_BYTES))
        if used + amount > MAX_CAPTURE_BYTES:
            return False
        used += amount
        return True

    # Required selectors take precedence, including over automatic name collisions.
    for binding in request.required_metrics:
        try:
            metric = capture_metric(binding.name, namespace[binding.binding])
            if not admits(metric):
                raise ValueError
            metrics[binding.name] = metric
        except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
            return WorkerFinished(status="failed", diagnostic="metric_capture_failed")
    for name in request.parameters:
        if name not in namespace:
            continue
        try:
            parameter = Parameter.model_validate(
                {
                    "name": name,
                    "value": namespace[name],
                    "origin": EvidenceOrigin.RUNTIME,
                }
            )
            if admits(parameter):
                parameters.append(parameter)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            continue
    for binding in request.automatic_metrics:
        if binding.name in metrics:
            continue
        if len(metrics) == 256:
            break
        try:
            metric = capture_metric(binding.name, namespace[binding.binding])
            if admits(metric):
                metrics[binding.name] = metric
        except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
            continue
    return WorkerFinished(
        status="success", parameters=tuple(parameters), metrics=tuple(metrics.values())
    )


def execute(
    request: WorkloadRequest, started: Callable[[WorkerStarted], None]
) -> WorkerFinished:
    executable = request.executable_bytes()
    root = Path.cwd()
    environment = capture_runtime_environment(
        distributions=request.distributions, root=root
    ).evidence
    started(WorkerStarted(environment=environment))
    try:
        current = read_regular(root / request.subject.reference, 16 * 1024**2)
        if sha256(current).hexdigest() != request.subject.digest:
            raise ValueError
    except (OSError, ValueError):
        return WorkerFinished(status="failed", diagnostic="source_changed")
    inputs = fingerprint_inputs(root, request.inputs, policy=request.fingerprint_policy)
    if any(
        (expected.digest is not None and expected.digest != actual.digest)
        or (expected.size is not None and expected.size != actual.size)
        for expected, actual in zip(request.inputs, inputs.artifacts, strict=True)
    ):
        return WorkerFinished(status="failed", diagnostic="input_changed")
    # Normal script module identity, while deliberately adding only the selected
    # project root rather than relying on ambient PYTHONPATH or importing source.
    module = types.ModuleType("__main__")
    module.__file__ = request.subject.reference
    module.__package__ = None
    sys.modules["__main__"] = module
    sys.argv = [request.subject.reference]
    sys.path.insert(0, str(root))
    try:
        exec(compile(executable, request.subject.reference, "exec"), module.__dict__)
    except SystemExit as error:
        if error.code is not None and error.code != 0:
            return WorkerFinished(status="failed", diagnostic="execution_exit")
    except KeyboardInterrupt:
        return WorkerFinished(status="cancelled", diagnostic="execution_cancelled")
    except BaseException:
        return WorkerFinished(status="failed", diagnostic="execution_exception")
    return observe(request, module.__dict__)


def main() -> None:
    # This duplicate is non-inheritable. print/os.write(1) and stderr go to the
    # parent's DEVNULL; user output cannot become protocol framing or stored logs.
    descriptor = os.dup(1)
    os.dup2(2, 1)
    with os.fdopen(descriptor, "wb") as output:

        def send(message: WorkerStarted | WorkerFinished) -> None:
            output.write(
                frame(encode(message.model_dump(mode="json"), MAX_RESPONSE_BYTES))
            )
            output.flush()

        try:
            raw = read_frame(sys.stdin.buffer, MAX_REQUEST_BYTES)
            request = WorkloadRequest.model_validate_json(
                encode(raw, MAX_REQUEST_BYTES)
            )
            result = execute(request, send)
        except BaseException:
            result = WorkerFinished(status="failed", diagnostic="worker_failed")
        send(result)


if __name__ == "__main__":
    main()
