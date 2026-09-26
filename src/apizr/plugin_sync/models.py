"""Additive synchronization outcomes, not a transaction or activation request."""

from typing import Literal

from pydantic import Field

from apizr.capabilities.types import ValueModel
from apizr.local_plugins.models import Digest
from apizr.plugin_lock.models import Diagnostic, Target


class SyncLimits(ValueModel):
    timeout_ms: int = Field(default=120000, ge=1, le=600000, strict=True)


class PluginAction(ValueModel):
    name: str
    version: str
    action: Literal["install", "reuse", "refuse"]
    status: Literal[
        "planned",
        "not_attempted",
        "installed",
        "reused",
        "refused",
        "failed",
        "unconfirmed",
    ] = "not_attempted"
    active: bool | None = None
    interpreter_verified: bool = False


class SyncResult(ValueModel):
    schema_version: Literal["apizr.plugin-sync/v1"] = "apizr.plugin-sync/v1"
    mode: Literal["dry-run", "apply"]
    state: Literal[
        "planned", "complete", "refused", "partial", "interrupted", "unconfirmed"
    ]
    exit_code: Literal[0, 1, 2, 130]
    lock_sha256: Digest | None = None
    target: Target | None = None
    plugins: tuple[PluginAction, ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
