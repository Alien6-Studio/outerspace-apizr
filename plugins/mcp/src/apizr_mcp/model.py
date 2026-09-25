"""Strict MCP arguments and startup snapshots; compiler contracts remain canonical."""

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.exposure import ExposurePolicy
from apizr.graph import Graph, GraphPolicy
from apizr.repository import Catalog, ScanPolicy
from apizr.repository_readiness import (
    RepositoryReadinessPolicy,
    RepositoryReadinessReport,
)


class StrictModel(ValueModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Arguments(StrictModel):
    expected_repository_digest: (
        Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    ) = None


class PlanArguments(Arguments):
    policy: ExposurePolicy | None = None


class ServerLimits(StrictModel):
    timeout_ms: int = Field(default=10000, ge=1, le=600000)
    max_request_bytes: int = Field(default=65536, ge=4096, le=1048576)
    max_response_bytes: int = Field(default=4194304, ge=2048, le=16777216)


class Scope(StrictModel):
    root: str
    device: int
    inode: int
    scan: ScanPolicy
    graph: GraphPolicy
    readiness: RepositoryReadinessPolicy
    exposure: ExposurePolicy | None


Operation = Literal["analyze", "readiness", "plan"]


class Job(StrictModel):
    scope: Scope
    arguments: PlanArguments
    operation: Operation


class AnalysisResult(ValueModel):
    repository_digest: Digest
    catalog: Catalog
    graph: Graph


class ReadinessResult(ValueModel):
    repository_digest: Digest
    report: RepositoryReadinessReport
    exit_code: Literal[0, 1]
