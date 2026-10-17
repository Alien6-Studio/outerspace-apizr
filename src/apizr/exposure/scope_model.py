"""Immutable selected-evidence results; no source access or proof computation."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from apizr.graph.model import Code as GraphCode
from apizr.readiness.model import Code as LocalCode
from apizr.readiness.model import State
from apizr.repository.model import Code as CatalogCode
from apizr.repository_readiness.model import Reason


@dataclass(frozen=True)
class ScopeIssue:
    capability_id: str | None
    dependency_path: tuple[str, ...]
    source_path: str | None
    line: int | None
    column: int | None
    evidence_code: GraphCode | CatalogCode | LocalCode
    reason: Literal[
        "global", "diagnostic", "initialization", "binding", "execution", "import"
    ]


@dataclass(frozen=True)
class ScopedRoot:
    state: State
    interface_eligible: bool
    reasons: tuple[Reason, ...]
    required_ids: tuple[str, ...]
    issues: tuple[ScopeIssue, ...]


@dataclass(frozen=True)
class EvidenceScope:
    roots: Mapping[str, ScopedRoot]
    global_issues: tuple[ScopeIssue, ...]

    @property
    def issues(self) -> tuple[ScopeIssue, ...]:
        return self.global_issues + tuple(
            issue for root in self.roots.values() for issue in root.issues
        )
