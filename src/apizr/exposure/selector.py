"""Exact selection only; no dependency traversal or implicit publication."""

from apizr.readiness.model import State
from apizr.repository_readiness.model import RepositoryReadinessReport

from .policy import Selection


def select_ids(
    report: RepositoryReadinessReport, selection: Selection
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    known = {a.capability_id for a in report.assessments}
    unknown = (set(selection.include) | set(selection.exclude)) - known
    chosen = set(selection.include)
    if selection.include_all_ready:
        chosen.update(
            a.capability_id for a in report.assessments if a.state == State.READY
        )
    chosen.difference_update(selection.exclude)
    return tuple(sorted(chosen & known)), tuple(sorted(unknown))
