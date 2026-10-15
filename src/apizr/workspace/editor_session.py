"""Explicit read-only editor/history composition over canonical engine operations."""

from pathlib import Path

from apizr.contracts.analysis import LocalTarget
from apizr.editor_contracts.discovery import capabilities
from apizr.editor_contracts.model import (
    DiffArguments,
    EditorDiagnostic,
    EditorRequest,
    EditorResponse,
    InspectArguments,
    ListArguments,
    PlanArguments,
    Result,
    ShowArguments,
)
from apizr.environment.extras import MissingExtra
from apizr.experiments.comparison import compare_stored_runs
from apizr.experiments.history import HistoryQuery, list_runs, show_run
from apizr.experiments.store import DEFAULT_STORE, StoreError
from apizr.exposure import ExposureRefused, plan_exposure
from apizr.graph import analyze_repository
from apizr.repository_readiness import assess_repository
from apizr.workspace.analysis_session import Scope, check_scope
from apizr.workspace.operator_policy import AuthorizationDenied, decide_history

DEFAULT_STORE_REFERENCE = DEFAULT_STORE.as_posix()


def history_value(
    scope: Scope, request: EditorRequest, *, store: str = DEFAULT_STORE_REFERENCE
) -> Result:
    """Both transports call this dispatch; all record validation/diffing stays in experiments."""
    decision = decide_history(
        scope.operator_policy, LocalTarget(root=scope.root), store
    )
    if not decision.allowed:
        raise AuthorizationDenied(decision.code)
    check_scope(scope)
    path = Path(scope.root) / store
    arguments = request.arguments
    if request.operation == "experiment_list" and isinstance(arguments, ListArguments):
        value = list_runs(
            path,
            query=HistoryQuery.model_validate_json(arguments.model_dump_json()),
            include_values=True,
        )
    elif request.operation == "experiment_show" and isinstance(
        arguments, ShowArguments
    ):
        value = show_run(path, arguments.run_id)
    elif request.operation == "experiment_diff" and isinstance(
        arguments, DiffArguments
    ):
        value = compare_stored_runs(path, arguments.run_a, arguments.run_b)
    else:
        raise ValueError("history_operation_invalid")
    check_scope(scope)
    return value


def history_error(error: StoreError) -> str:
    code = str(error)
    return (
        code
        if code in {"run_not_found", "run_id_ambiguous", "run_id_invalid"}
        else "history_invalid"
    )


MESSAGES = {
    "project_required": "Select a project and operator policy before requesting project evidence.",
    "invalid_request": "Use a supported apizr.editor/v1 request with the documented arguments.",
    "request_too_large": "Reduce the request to at most 65536 bytes.",
    "response_too_large": "The result exceeds the response limit; reduce the history list limit or inspect a smaller source.",
    "history_invalid": "The complete local history could not be validated; inspect the store without changing retained evidence.",
    "run_not_found": "No retained Run matches this identity.",
    "run_id_ambiguous": "Several retained Runs match this prefix; use the complete Run digest.",
    "run_id_invalid": "Use a lowercase Run digest or a unique prefix of at least 12 characters.",
    "policy_required": "Provide an explicit exposure policy or configure the startup project policy.",
    "exposure_refused": "The exposure proposal was refused by the existing readiness and exposure policy.",
    "extra_required": "Install the engine's notebook extra to inspect saved notebooks.",
    "operation_failed": "The engine could not read valid bounded evidence; check the saved source, project and configured limits.",
    "source_outside_scope": "Select a saved source inside the project's configured source roots, exclusions and depth limits.",
}


def failure(code: str, request: EditorRequest | None = None) -> EditorResponse:
    return EditorResponse(
        request_id=request.request_id if request else None,
        operation=request.operation if request else None,
        ok=False,
        diagnostics=(
            EditorDiagnostic(
                code=code,
                message=MESSAGES.get(
                    code,
                    "Operator authorization or the captured project scope refused this request; review startup configuration.",
                ),
                severity="error",
            ),
        ),
    )


def execute(
    request: EditorRequest,
    scope: Scope | None = None,
    *,
    store: str = DEFAULT_STORE_REFERENCE,
) -> EditorResponse:
    request = EditorRequest.model_validate_json(request.model_dump_json(), strict=True)
    diagnostics: tuple[EditorDiagnostic, ...] = ()
    try:
        if request.operation == "capabilities":
            value: Result = capabilities()
        elif scope is None:
            return failure("project_required", request)
        elif request.operation.startswith("experiment_"):
            value = history_value(scope, request, store=store)
        else:
            check_scope(scope)
            arguments = request.arguments
            if isinstance(arguments, InspectArguments):
                from apizr.experiments.inspection import inspect_experiment

                source = Path(arguments.source)
                admitted = any(
                    source.is_relative_to(Path(root))
                    and len(source.relative_to(root).parts) - 1 <= scope.scan.max_depth
                    for root in scope.scan.source_roots
                )
                if not admitted or set(source.parts[:-1]) & set(
                    scope.scan.excluded_directories
                ):
                    return failure("source_outside_scope", request)
                value = inspect_experiment(
                    Path(scope.root) / arguments.source,
                    root=scope.root,
                    module_name=arguments.module_name,
                    max_source_bytes=min(
                        scope.scan.max_file_bytes, scope.scan.max_total_bytes
                    ),
                )
                locations = {item.evidence: item.location for item in value.locations}
                diagnostics = tuple(
                    EditorDiagnostic(
                        code=d.code.value,
                        message="Static inspection observation; see the canonical inspection result for its evidence and uncertainty.",
                        severity=d.severity.value,
                        location=locations.get(f"/code/diagnostics/{index}"),
                    )
                    for index, d in enumerate(value.code.diagnostics)
                )
            elif isinstance(arguments, PlanArguments):
                policy = (
                    arguments.policy if arguments.policy is not None else scope.exposure
                )
                if policy is None:
                    return failure("policy_required", request)
                evidence = analyze_repository(
                    scope.source(),
                    scan_policy=scope.scan,
                    graph_policy=scope.graph,
                    operator_policy=scope.operator_policy,
                )
                readiness = assess_repository(
                    evidence.catalog, evidence.graph, policy=scope.readiness
                )
                value = plan_exposure(
                    evidence.catalog, evidence.graph, readiness, policy=policy
                )
            else:
                return failure("invalid_request", request)
            check_scope(scope)
        return EditorResponse(
            request_id=request.request_id,
            operation=request.operation,
            ok=True,
            value=value,
            diagnostics=diagnostics,
        )
    except AuthorizationDenied as error:
        return failure(error.code, request)
    except StoreError as error:
        return failure(history_error(error), request)
    except ExposureRefused as error:
        response = failure("exposure_refused", request)
        return EditorResponse.model_validate(
            response.model_copy(update={"exposure_diagnostics": error.diagnostics})
        )
    except MissingExtra:
        return failure("extra_required", request)
    except (OSError, ValueError, SyntaxError, UnicodeError, RecursionError):
        return failure("operation_failed", request)
