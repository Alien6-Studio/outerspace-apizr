"""Strict MCP arguments and startup snapshots; compiler contracts remain canonical."""

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, RootModel, model_validator

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.exposure import ExposurePolicy
from apizr.graph import Graph
from apizr.repository import Catalog
from apizr.repository_readiness import (
    RepositoryReadinessReport,
)
from apizr.repository_views.model import (
    MAX_LIMIT,
    AnalysisDetail,
    AnalysisSummary,
    ReadinessDetail,
    ReadinessSummary,
    ViewQuery,
)
from apizr.workspace.analysis_session import Scope as Scope


class StrictModel(ValueModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Arguments(StrictModel):
    expected_repository_digest: (
        Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    ) = None


class PlanArguments(Arguments):
    policy: ExposurePolicy | None = None
    offset: int | None = Field(default=None, ge=0, le=2147483647)
    limit: int | None = Field(default=None, ge=1, le=MAX_LIMIT)

    @model_validator(mode="after")
    def continuation(self) -> Self:
        if self.offset and self.expected_repository_digest is None:
            raise ValueError("Continuation requires the repository digest")
        return self


class ViewArguments(ViewQuery):
    pass


class DeliveryStatusArguments(StrictModel):
    pass


class DeliveryArguments(StrictModel):
    expected_delivery_manifest_digest: Digest


class ServerLimits(StrictModel):
    timeout_ms: int = Field(default=10000, ge=1, le=600000)
    max_request_bytes: int = Field(default=65536, ge=4096, le=1048576)
    max_response_bytes: int = Field(default=4194304, ge=2048, le=16777216)


Operation = Literal["analyze", "readiness", "plan"]


class Job(StrictModel):
    scope: Scope
    arguments: ViewArguments | PlanArguments
    operation: Operation

    @model_validator(mode="after")
    def operation_arguments(self) -> Self:
        if self.operation == "plan":
            if (
                isinstance(self.arguments, ViewArguments)
                and self.arguments.view != "full"
            ):
                raise ValueError("Planning does not accept analysis views")
        elif isinstance(self.arguments, PlanArguments) and (
            self.arguments.policy is not None
            or self.arguments.offset is not None
            or self.arguments.limit is not None
        ):
            raise ValueError("Analysis does not accept planning arguments")
        return self


class AnalysisResult(ValueModel):
    repository_digest: Digest
    catalog: Catalog
    graph: Graph


class ReadinessResult(ValueModel):
    repository_digest: Digest
    report: RepositoryReadinessReport
    exit_code: Literal[0, 1]


class AnalysisOutput(RootModel[AnalysisResult | AnalysisSummary | AnalysisDetail]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class ReadinessOutput(RootModel[ReadinessResult | ReadinessSummary | ReadinessDetail]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})
