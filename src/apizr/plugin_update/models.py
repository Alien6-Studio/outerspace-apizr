"""Separate preparation, activation and observed state in update results."""

from typing import Literal

from apizr.capabilities.types import ValueModel
from apizr.local_plugins.models import Digest, Installation, Version
from apizr.plugin_lock.models import Diagnostic, Plugin, Target


class UpdateResult(ValueModel):
    schema_version: Literal["apizr.plugin-update/v1"] = "apizr.plugin-update/v1"
    mode: Literal["dry-run", "apply"]
    state: Literal[
        "planned", "complete", "refused", "partial", "interrupted", "unconfirmed"
    ] = "refused"
    exit_code: Literal[0, 1, 2, 130] = 2
    plugin: str | None = None
    from_version: Version | None = None
    source: Installation | None = None
    target: Plugin | None = None
    target_installation: Installation | None = None
    python_target: Target | None = None
    lock_sha256: Digest | None = None
    installation: Literal[
        "not_attempted", "planned", "reused", "installed", "failed", "unconfirmed"
    ] = "not_attempted"
    interpreter_verified: bool = False
    activation_requested: bool = False
    activation: Literal[
        "not_requested",
        "not_attempted",
        "planned",
        "unchanged",
        "changed",
        "refused",
        "observed_target",
        "unconfirmed",
    ] = "not_requested"
    active_before: Installation | None = None
    active_after: Installation | None = None
    before_known: bool = False
    after_known: bool = False
    diagnostics: tuple[Diagnostic, ...] = ()
