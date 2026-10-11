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
    PIN_EXAMPLE,
    READINESS_EXIT_DESCRIPTION,
    REPOSITORY_PIN_DESCRIPTION,
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
    ) = Field(default=None, description=REPOSITORY_PIN_DESCRIPTION)


class PlanArguments(Arguments):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {},
                {"expected_repository_digest": PIN_EXAMPLE},
                {
                    "policy": {
                        "selection": {"include": ["python:model:predict"]},
                        "interfaces": ["mcp"],
                        "execution": {"allowed": ["direct"]},
                    }
                },
            ]
        }
    )

    policy: ExposurePolicy | None = Field(
        default=None,
        description=(
            "Explicit proposal policy to use for this plan. Omitted/null uses the startup "
            "exposure policy if present; if neither exists, returns policy_required. "
            "ExposurePolicy is a planning constraint, not operator authority: it cannot "
            "enlarge startup permissions or authorize generation, execution or publication."
        ),
    )
    offset: int | None = Field(
        default=None,
        ge=0,
        le=2147483647,
        description=(
            "Optional zero-based offset into deterministically ordered refused-plan "
            "diagnostics; defaults to 0. A nonzero offset requires expected_repository_digest. "
            "Successful canonical plans are never paginated; there is no server-side session."
        ),
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_LIMIT,
        description=(
            "Optional refused-plan diagnostic page size, from 1 to 200; omitted/null uses "
            "50 when pagination is requested. With offset and limit both omitted/null, "
            "all refusal diagnostics are returned. Successful plans remain unchanged."
        ),
    )

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
    expected_delivery_manifest_digest: Digest = Field(
        description=(
            "Exact delivery manifest identity of the operator-selected existing build. "
            "Copy the complete algorithm/value object from apizr_delivery_status after "
            "reviewing its evidence. A mismatch refuses delivery; this pin neither "
            "selects another build nor grants authority or permits a blind retry."
        )
    )


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
    repository_digest: Digest = Field(
        description="Repository evidence identity observed by this call; copy value to expected_repository_digest to pin a subsequent call."
    )
    catalog: Catalog = Field(
        description="Complete canonical static capability and source evidence; does not imply successful project execution."
    )
    graph: Graph = Field(
        description="Complete canonical static relationship and import graph evidence, including uncertainty; does not imply successful project execution."
    )


class ReadinessResult(ValueModel):
    repository_digest: Digest = Field(
        description="Repository evidence identity observed by this call; copy value to expected_repository_digest to pin a subsequent call."
    )
    report: RepositoryReadinessReport = Field(
        description="Complete canonical static readiness assessment under the startup policy. READY, CONDITIONAL, AMBIGUOUS and UNSUPPORTED remain distinct; unknown evidence is retained. This is not proof of successful execution."
    )
    exit_code: Literal[0, 1] = Field(description=READINESS_EXIT_DESCRIPTION)


class AnalysisOutput(RootModel[AnalysisResult | AnalysisSummary | AnalysisDetail]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})


class ReadinessOutput(RootModel[ReadinessResult | ReadinessSummary | ReadinessDetail]):
    model_config = ConfigDict(json_schema_extra={"type": "object"})
