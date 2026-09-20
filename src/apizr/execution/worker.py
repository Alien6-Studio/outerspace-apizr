"""The only execution component that imports trusted capability source."""

import asyncio
import os
import sys
from pathlib import Path

from apizr.capabilities.model import Digest
from apizr.interfaces.runtime import (
    BindingError,
    IntegrityError,
    SourcePlan,
    arguments,
    load_source,
    verify_binding,
)

from .invocation import runtime_contract, validate_arguments
from .model import ExecutionResult, Request
from .planner import validate_plan
from .policy import PolicyRefused
from .protocol import (
    MAX_REQUEST_BYTES,
    SizeExceeded,
    encode,
    finite_json,
    frame,
    read_frame,
)
from .serialization import digest


def handle(request: Request, root: Path) -> ExecutionResult:
    policy = request.plan.policy
    try:
        if request.plan_digest != digest(request.plan):
            return ExecutionResult(status="binding_failed")
        validate_arguments(request.plan.interface, request.arguments)
        encode(request.arguments, policy.limits.max_input_bytes)
    except (ValueError, RecursionError):
        return ExecutionResult(status="invalid_input")
    try:
        original = (root / "original").read_bytes()
        # Path is recomputed from the validated IR identity, not an arbitrary wire path.
        executable_path = (
            "source/"
            + request.plan.inspection.capability_ir.source.module.replace(".", "/")
            + ".py"
        )
        executable = (root / executable_path).read_bytes()
        if Digest.of_bytes(executable) != request.plan.executable_digest:
            return ExecutionResult(status="source_mismatch")
        validated = validate_plan(request.plan, original, executable)
    except PolicyRefused:
        return ExecutionResult(status="policy_refused")
    except (OSError, ValueError, RecursionError):
        return ExecutionResult(status="binding_failed")
    binding = runtime_contract(validated.interface)
    source_plan: SourcePlan = {
        "executable_path": validated.executable_path,
        "executable_digest": {"value": validated.executable_digest.value},
        "source": {"module": validated.source.module},
    }
    try:
        module = load_source(root, source_plan)
        function = verify_binding(module, binding)
    except IntegrityError:
        return ExecutionResult(status="source_mismatch")
    except BindingError:
        return ExecutionResult(status="binding_failed")
    except BaseException:
        return ExecutionResult(status="execution_failed")
    try:
        args, kwargs = arguments(function, binding, request.arguments)
        if binding["execution"] == "async":
            result = asyncio.run(function(*args, **kwargs))
        else:
            result = function(*args, **kwargs)
    except BaseException:
        return ExecutionResult(status="execution_failed")
    try:
        outcome = ExecutionResult(status="success", value=finite_json(result))
        encode(outcome.model_dump(mode="json"), policy.limits.max_output_bytes)
        return outcome
    except SizeExceeded:
        return ExecutionResult(status="output_limit")
    except (ValueError, TypeError, RecursionError):
        return ExecutionResult(status="result_invalid")


def main() -> None:
    # Reserve a private non-inheritable duplicate for protocol output. Ordinary
    # print/os.write(1, ...) and stderr never mix with the response frame.
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    limit = 128
    try:
        request = Request.model_validate(
            read_frame(sys.stdin.buffer, MAX_REQUEST_BYTES)
        )
        limit = request.plan.policy.limits.max_output_bytes
        outcome = handle(request, Path.cwd())
    except BaseException:
        outcome = ExecutionResult(status="worker_failed")
    with os.fdopen(protocol_fd, "wb") as output:
        output.write(frame(encode(outcome.model_dump(mode="json"), limit)))
        output.flush()


if __name__ == "__main__":
    main()
