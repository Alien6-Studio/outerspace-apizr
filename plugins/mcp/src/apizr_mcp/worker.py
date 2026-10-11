"""One isolated compiler call. No MCP SDK, imports of project code, or CLI calls."""

import json
import sys

from pydantic import ValidationError

from apizr.exposure import ExposureRefused, plan_bytes, plan_exposure
from apizr.extension_runtime.protocol import Request, unique_object
from apizr.graph import analyze_repository
from apizr.graph.serialization import graph_bytes
from apizr.repository.serialization import catalog_bytes
from apizr.repository_readiness import assess_repository
from apizr.repository_readiness.serialization import report_bytes
from apizr.repository_views.model import DEFAULT_LIMIT, Page
from apizr.repository_views.projection import (
    ViewRefused,
    analyze_view,
    localize,
    readiness_view,
)
from apizr.workspace.operator_policy import AuthorizationDenied

from .model import Job, PlanArguments, ViewArguments

MAX_JOB_BYTES = 1048576


def failure(
    code: str, *, diagnostics: list | None = None, page: Page | None = None
) -> dict:
    error = {"code": code, "diagnostics": diagnostics or []}
    if page is not None:
        error.update(page=page.model_dump(mode="json"), diagnostic_count=page.total)
    return {"ok": False, "error": error}


def calculate(job: Job) -> dict:
    scope = job.scope
    try:
        source = scope.source()
        options = {"scan_policy": scope.scan, "graph_policy": scope.graph}
        policy = (
            job.arguments.policy
            if isinstance(job.arguments, PlanArguments)
            and job.arguments.policy is not None
            else scope.exposure
        )
        if job.operation == "plan" and policy is None:
            return failure("policy_required")
        evidence = analyze_repository(
            source, **options, operator_policy=scope.operator_policy
        )
        digest = evidence.catalog.repository_digest
        if (
            job.arguments.expected_repository_digest is not None
            and digest.value != job.arguments.expected_repository_digest
        ):
            return failure("repository_changed")
        query = (
            job.arguments
            if isinstance(job.arguments, ViewArguments)
            else ViewArguments(
                expected_repository_digest=job.arguments.expected_repository_digest
            )
        )
        report = (
            assess_repository(evidence.catalog, evidence.graph, policy=scope.readiness)
            if job.operation != "analyze" or query.view == "detail"
            else None
        )
        if job.operation == "analyze":
            value = (
                {
                    "repository_digest": digest.model_dump(mode="json"),
                    "catalog": json.loads(catalog_bytes(evidence.catalog)),
                    "graph": json.loads(graph_bytes(evidence.graph)),
                }
                if query.view == "full"
                else analyze_view(
                    evidence.catalog, evidence.graph, query, report
                ).model_dump(mode="json")
            )
        elif job.operation == "readiness":
            assert report is not None
            value = (
                {
                    "repository_digest": digest.model_dump(mode="json"),
                    "report": json.loads(report_bytes(report)),
                    "exit_code": report.exit_code,
                }
                if query.view == "full"
                else readiness_view(
                    evidence.catalog, evidence.graph, report, query
                ).model_dump(mode="json")
            )
        else:
            assert report is not None and policy is not None
            value = json.loads(
                plan_bytes(
                    plan_exposure(
                        evidence.catalog, evidence.graph, report, policy=policy
                    )
                )
            )
        return {"ok": True, "value": value}
    except ExposureRefused as error:
        diagnostics = tuple(localize(d) for d in error.diagnostics)
        page = None
        if isinstance(job.arguments, PlanArguments) and (
            job.arguments.offset is not None or job.arguments.limit is not None
        ):
            offset, limit = (
                job.arguments.offset or 0,
                job.arguments.limit or DEFAULT_LIMIT,
            )
            total = len(diagnostics)
            diagnostics = diagnostics[offset : offset + limit]
            more = offset + len(diagnostics) < total
            page = Page(
                offset=offset,
                limit=limit,
                total=total,
                returned=len(diagnostics),
                next_offset=offset + len(diagnostics) if more else None,
                complete=not more,
            )
        return failure(
            "exposure_refused",
            diagnostics=[d.model_dump(mode="json") for d in diagnostics],
            page=page,
        )
    except ViewRefused as error:
        return failure(error.code)
    except AuthorizationDenied as error:
        code = error.decision.code
        return failure("scope_changed" if code == "operator_source_changed" else code)


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
