"""Closed editor requests over the engine's existing evidence contracts."""

import json
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, RootModel, model_validator

from apizr.experiments.comparison import ExperimentDiff, ExperimentDiffV2
from apizr.experiments.history import HistoryList, HistoryListV2, HistoryQuery
from apizr.experiments.inspection_model import ExperimentInspection
from apizr.experiments.model import ExperimentValue, Name, Reference
from apizr.experiments.notebook_source import SourceLocation
from apizr.experiments.store import RunRecord, RunRecordV2
from apizr.exposure import ExposurePlan, ExposurePolicy
from apizr.exposure.planner import Diagnostic as ExposureDiagnostic
from apizr.scientific_providers.contracts import ProviderDescriptor

Operation = Literal[
    "capabilities",
    "inspect",
    "experiment_list",
    "experiment_show",
    "experiment_diff",
    "plan_exposure",
]
RunId = Annotated[str, Field(pattern=r"^[0-9a-f]{12,64}$")]
EditorReference = Annotated[
    Reference,
    Field(
        json_schema_extra={
            "pattern": r"^(?!~)(?!/)(?!.*(?:^|/)\.{1,2}(?:/|$))(?!.*[\\:\x00-\x1f\x7f])[^/]+(?:/[^/]+)*$"
        }
    ),
]


class NoArguments(ExperimentValue):
    pass


class InspectArguments(ExperimentValue):
    source: EditorReference = Field(
        description="Saved Python script or notebook relative to the operator-selected project root."
    )
    module_name: Name | None = Field(
        default=None,
        description="Optional logical Python module name; omitted uses the saved file stem.",
    )


class ListArguments(HistoryQuery):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{}, {"status": "failed", "limit": 5}]}
    )
    status: Literal["success", "failed", "cancelled"] | None = Field(
        default=None,
        description="Optional exact recorded status; all records are validated before this display filter.",
    )
    source: EditorReference | None = Field(
        default=None,
        description="Optional exact recorded project-relative source reference, never a filesystem target.",
    )
    capability: Annotated[str, Field(min_length=1, max_length=512)] | None = Field(
        default=None,
        description="Optional exact recorded capability identity; SDK sessions may have none.",
    )
    limit: Annotated[int, Field(ge=1, le=1000)] = Field(
        default=20,
        description="Maximum displayed Runs, from 1 to 1000; does not reduce validation of the complete bounded history.",
    )


class ShowArguments(ExperimentValue):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"run_id": "0123456789ab"}]}
    )
    run_id: RunId = Field(
        description="Full recorded Run SHA-256 or unique lowercase prefix of 12 to 64 hexadecimal characters; ambiguity refuses the request."
    )


class DiffArguments(ExperimentValue):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"run_a": "0123456789ab", "run_b": "abcdef012345"}]
        }
    )
    run_a: RunId = Field(
        description="First recorded Run identity or unique lowercase prefix; comparison is directional from A to B."
    )
    run_b: RunId = Field(
        description="Second recorded Run identity or unique lowercase prefix; differences describe evidence, never causality."
    )


class PlanArguments(ExperimentValue):
    policy: ExposurePolicy | None = Field(
        default=None,
        description="Explicit proposal policy, or the startup project policy when omitted; grants no generation or execution authority.",
    )


ARGUMENT_MODELS = {
    "capabilities": NoArguments,
    "inspect": InspectArguments,
    "experiment_list": ListArguments,
    "experiment_show": ShowArguments,
    "experiment_diff": DiffArguments,
    "plan_exposure": PlanArguments,
}
Arguments = (
    NoArguments
    | InspectArguments
    | ListArguments
    | ShowArguments
    | DiffArguments
    | PlanArguments
)


def _request_schema(schema: dict) -> None:
    schema["allOf"] = [
        {
            "if": {"properties": {"operation": {"const": operation}}},
            "then": {
                "properties": {"arguments": reference},
                **(
                    {"required": ["arguments"]}
                    if operation in {"inspect", "experiment_show", "experiment_diff"}
                    else {}
                ),
            },
        }
        for (operation, _), reference in zip(
            ARGUMENT_MODELS.items(),
            schema["properties"]["arguments"]["anyOf"],
            strict=True,
        )
    ]


class EditorRequest(ExperimentValue):
    model_config = ConfigDict(json_schema_extra=_request_schema)
    schema_version: Literal["apizr.editor/v1"] = "apizr.editor/v1"
    request_id: Annotated[
        str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    ] = "request"
    operation: Operation
    arguments: Arguments = NoArguments()

    @model_validator(mode="before")
    @classmethod
    def operation_arguments(cls, value):
        if (
            isinstance(value, dict)
            and isinstance(value.get("operation"), str)
            and value["operation"] in ARGUMENT_MODELS
        ):
            value = dict(value)
            arguments = value.get("arguments", {})
            if isinstance(arguments, ExperimentValue):
                arguments = arguments.model_dump(mode="json")
            try:
                value["arguments"] = ARGUMENT_MODELS[
                    value["operation"]
                ].model_validate_json(json.dumps(arguments), strict=True)
            except (ValueError, TypeError, RecursionError):
                raise ValueError("editor_arguments_invalid") from None
        return value


class OperationCapability(ExperimentValue):
    name: Operation
    result_schemas: Annotated[tuple[Name, ...], Field(min_length=1, max_length=3)]
    required_permissions: tuple[Literal["source.analyze", "experiments.read"], ...]
    read_only: Literal[True] = True


class EngineCapabilities(ExperimentValue):
    schema_version: Literal["apizr.editor-capabilities/v1"] = (
        "apizr.editor-capabilities/v1"
    )
    protocol: Literal["apizr.editor/v1"] = "apizr.editor/v1"
    engine_version: Name
    operations: Annotated[
        tuple[OperationCapability, ...], Field(min_length=6, max_length=6)
    ]
    providers: Annotated[tuple[ProviderDescriptor, ...], Field(max_length=128)]
    max_request_bytes: Literal[65536] = 65536
    max_response_bytes: Literal[4194304] = 4194304


class EditorDiagnostic(ExperimentValue):
    code: Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,95}$")]
    message: Annotated[str, Field(min_length=1, max_length=1024)]
    severity: Literal["error", "warning", "info"]
    location: SourceLocation | None = None


class HistoryOutput(RootModel[HistoryList | HistoryListV2]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class RecordOutput(RootModel[RunRecord | RunRecordV2]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class DiffOutput(RootModel[ExperimentDiff | ExperimentDiffV2]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


Result = (
    EngineCapabilities
    | ExperimentInspection
    | HistoryList
    | HistoryListV2
    | RunRecord
    | RunRecordV2
    | ExperimentDiff
    | ExperimentDiffV2
    | ExposurePlan
)


class EditorResponse(ExperimentValue):
    schema_version: Literal["apizr.editor-response/v1"] = "apizr.editor-response/v1"
    request_id: str | None = Field(default=None, max_length=64)
    operation: Operation | None = None
    ok: bool
    value: Result | None = None
    diagnostics: Annotated[tuple[EditorDiagnostic, ...], Field(max_length=1024)] = ()
    exposure_diagnostics: tuple[ExposureDiagnostic, ...] = ()

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.ok != (self.value is not None):
            raise ValueError("editor_response_state_invalid")
        if self.ok and (self.operation is None or self.request_id is None):
            raise ValueError("editor_response_identity_required")
        if not self.ok and not self.diagnostics:
            raise ValueError("editor_failure_diagnostic_required")
        if self.ok:
            assert self.operation is not None
            outputs = {
                "capabilities": (EngineCapabilities,),
                "inspect": (ExperimentInspection,),
                "experiment_list": (HistoryList, HistoryListV2),
                "experiment_show": (RunRecord, RunRecordV2),
                "experiment_diff": (ExperimentDiff, ExperimentDiffV2),
                "plan_exposure": (ExposurePlan,),
            }
            if not isinstance(self.value, outputs[self.operation]):
                raise ValueError("editor_response_operation_mismatch")
        return self
