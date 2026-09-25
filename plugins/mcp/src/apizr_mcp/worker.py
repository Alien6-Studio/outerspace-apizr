"""One isolated compiler call. No MCP SDK, imports of project code, or CLI calls."""

import json
import os
import sys

from pydantic import ValidationError

from apizr.compiler import assess_readiness, prepare_exposure
from apizr.exposure import ExposureRefused, plan_bytes
from apizr.extension_runtime.protocol import Request, unique_object
from apizr.graph import analyze_repository
from apizr.graph.serialization import graph_bytes
from apizr.repository.serialization import catalog_bytes
from apizr.repository_readiness.serialization import report_bytes

from .model import Job
from .scope import open_root

MAX_JOB_BYTES = 1048576


def failure(code: str, *, diagnostics: list | None = None) -> dict:
    return {"ok": False, "error": {"code": code, "diagnostics": diagnostics or []}}


def calculate(job: Job) -> dict:
    scope = job.scope
    descriptor = open_root(scope.root)
    try:
        previous = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        os.close(descriptor)
        raise
    try:
        identity = os.fstat(descriptor)
        if (identity.st_dev, identity.st_ino) != (scope.device, scope.inode):
            return failure("scope_changed")
        # The scanner anchors '.' with its own descriptor. Ancestor replacement
        # cannot redirect this worker outside the repository inode selected at start.
        os.fchdir(descriptor)
        options = {"scan_policy": scope.scan, "graph_policy": scope.graph}
        if job.operation == "analyze":
            evidence = analyze_repository(".", **options)
            digest = evidence.catalog.repository_digest
            value = {
                "repository_digest": digest.model_dump(mode="json"),
                "catalog": json.loads(catalog_bytes(evidence.catalog)),
                "graph": json.loads(graph_bytes(evidence.graph)),
            }
        elif job.operation == "readiness":
            report = assess_readiness(".", **options, readiness_policy=scope.readiness)
            digest = report.repository_digest
            value = {
                "repository_digest": digest.model_dump(mode="json"),
                "report": json.loads(report_bytes(report)),
                "exit_code": report.exit_code,
            }
        else:
            policy = job.arguments.policy or scope.exposure
            if policy is None:
                return failure("policy_required")
            prepared = prepare_exposure(
                ".", **options, readiness_policy=scope.readiness, policy=policy
            )
            digest = prepared.plan.repository_digest
            value = json.loads(plan_bytes(prepared.plan))
        if (
            job.arguments.expected_repository_digest is not None
            and digest.value != job.arguments.expected_repository_digest
        ):
            return failure("repository_changed")
        return {"ok": True, "value": value}
    except ExposureRefused as error:
        return failure(
            "exposure_refused",
            diagnostics=[d.model_dump(mode="json") for d in error.diagnostics],
        )
    finally:
        os.fchdir(previous)
        os.close(previous)
        os.close(descriptor)


def main() -> int:
    try:
        raw = sys.stdin.buffer.read(MAX_JOB_BYTES + 1)
        if len(raw) > MAX_JOB_BYTES:
            raise ValueError()
        request = Request.model_validate(
            json.loads(raw, object_pairs_hook=unique_object), strict=True
        )
    except (ValueError, RecursionError):
        print("invalid_calculation_request", file=sys.stderr)
        return 2
    try:
        if request.operation != "calculate":
            raise ValueError()
        job = Job.model_validate_json(json.dumps(request.arguments), strict=True)
        result = calculate(job)
    except ValidationError:
        result = failure("invalid_arguments")
    except (OSError, ValueError, RecursionError):
        result = failure("operation_failed")
    response = {k: getattr(request, k) for k in ("protocol", "request_id", "operation")}
    response.update(status="ok", result=result)
    print(json.dumps(response, separators=(",", ":"), allow_nan=False))
    return 0
