"""Admission and descriptor anchoring for filesystem-backed repository analysis."""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from apizr.contracts.analysis import GitAnalysisTarget, LocalTarget, PinnedRoot
from apizr.git_source.models import GitSnapshot

if TYPE_CHECKING:
    from apizr.workspace.operator_policy import OperatorPolicy

RepositoryInput = str | Path | PinnedRoot | GitSnapshot


def open_root(root: str) -> int:
    """Traverse all path components without following links; caller closes the fd."""
    path = Path(root)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("invalid_root")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def open_analysis_root(
    source: RepositoryInput, operator_policy: "OperatorPolicy | None"
) -> int:
    """Refuse before traversal, then anchor the authorized tree (never read source bytes)."""
    from apizr.git_source.acquisition import snapshot_context
    from apizr.workspace.operator_policy import AuthorizationDenied, decide_analysis

    anchor: int | None = None
    pinned: PinnedRoot | None = None
    try:
        if isinstance(source, GitSnapshot):
            acquired, anchor = snapshot_context(source)
            target = GitAnalysisTarget(
                repository=acquired.repository,
                reference=acquired.reference,
                subdir=acquired.subdir,
            )
        elif isinstance(source, PinnedRoot):
            pinned = PinnedRoot.model_validate_json(
                source.model_dump_json(), strict=True
            )
            target = LocalTarget(root=pinned.root)
        else:
            target = LocalTarget(root=os.path.abspath(source))
    except (ValueError, TypeError, AttributeError):
        if anchor is not None:
            os.close(anchor)
        raise AuthorizationDenied("operator_source_invalid") from None
    except OSError:
        raise AuthorizationDenied("operator_source_unavailable") from None
    try:
        decision = decide_analysis(operator_policy, target)
        if not decision.allowed:
            raise AuthorizationDenied(decision.code)
        try:
            if anchor is not None:
                descriptor = os.dup(anchor)
            elif isinstance(target, LocalTarget):
                descriptor = open_root(target.root)
            else:
                raise AuthorizationDenied("operator_source_invalid")
        except OSError:
            raise AuthorizationDenied("operator_source_unavailable") from None
    finally:
        if anchor is not None:
            os.close(anchor)
    if pinned is not None:
        identity = os.fstat(descriptor)
        if (identity.st_dev, identity.st_ino) != (pinned.device, pinned.inode):
            os.close(descriptor)
            raise AuthorizationDenied("operator_source_changed")
    return descriptor
