"""Fresh repository worker: only this boundary imports project code."""

import asyncio
import importlib
import os
import sys
from pathlib import Path

from apizr.capabilities.model import Digest
from apizr.execution.invocation import runtime_contract, validate_arguments
from apizr.execution.model import ExecutionResult
from apizr.execution.policy import PolicyRefused, check_controls, local_capabilities
from apizr.execution.protocol import (
    MAX_REQUEST_BYTES,
    SizeExceeded,
    encode,
    finite_json,
    frame,
    read_frame,
)
from apizr.execution.serialization import digest
from apizr.interfaces.runtime import (
    BindingError,
    IntegrityError,
    arguments,
    verify_binding,
)
from apizr.repository_interfaces.runtime import RepositoryLoader, read_artifact

from .model import Request
from .planner import validate_plan, validate_sources


def handle(request: Request, root: Path) -> ExecutionResult:
    plan = request.plan
    if request.plan_digest != digest(plan):
        return ExecutionResult(status="binding_failed")
    try:
        encode(request.arguments, plan.policy.limits.max_input_bytes)
        validate_arguments(plan.interface, request.arguments)
    except (ValueError, RecursionError):
        return ExecutionResult(status="invalid_input")
    try:
        raw = read_artifact(root, "repository-interface.json")
        if Digest.of_bytes(raw) != plan.repository_interface_digest:
            raise ValueError("Repository interface changed")
        validate_plan(plan, read_artifact(root, "exposure-plan.json"))
        check_controls(plan.policy, local_capabilities())
        sources = {
            s.bundle_path: read_artifact(root, s.bundle_path)
            for s in plan.repository_interface.sources
        }
        validate_sources(plan.repository_interface, sources)
    except PolicyRefused:
        return ExecutionResult(status="policy_refused")
    except (OSError, ValueError, IntegrityError, RecursionError):
        return ExecutionResult(status="binding_failed")
    loader = RepositoryLoader(
        root, [s.model_dump(mode="json") for s in plan.repository_interface.sources]
    )
    binding = runtime_contract(plan.interface)
    try:
        try:
            loader.install()
            module = importlib.import_module(plan.capability_id.split(":")[1])
            function = verify_binding(module, binding)
        except IntegrityError:
            return ExecutionResult(status="source_mismatch")
        except BindingError:
            return ExecutionResult(status="binding_failed")
        except BaseException:
            return ExecutionResult(status="execution_failed")
        try:
            args, kwargs = arguments(function, binding, request.arguments)
            result = (
                asyncio.run(function(*args, **kwargs))
                if binding["execution"] == "async"
                else function(*args, **kwargs)
            )
        except BaseException:
            return ExecutionResult(status="execution_failed")
        try:
            outcome = ExecutionResult(status="success", value=finite_json(result))
            encode(outcome.model_dump(mode="json"), plan.policy.limits.max_output_bytes)
            return outcome
        except SizeExceeded:
            return ExecutionResult(status="output_limit")
        except (ValueError, TypeError, RecursionError):
            return ExecutionResult(status="result_invalid")
    finally:
        loader.close()


def main() -> None:
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
