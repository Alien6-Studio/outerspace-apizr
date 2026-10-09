"""SDK-independent, operator-captured MCP authority; no operational client input."""

import json
import os
import stat
from pathlib import Path

from pydantic import field_validator, model_validator

from apizr.analysis_session import MAX_SESSION_BYTES, Scope, check_scope
from apizr.delivery_batch import BatchRequest
from apizr.extension_runtime.protocol import unique_object
from apizr.operator_policy import AnalysisGrant, OperatorPolicy
from apizr.publication_contracts import Docker, Model
from apizr.workspace.files import read_regular

MAX_DELIVERY_REQUEST_BYTES = 524288


def analysis_scope(scope: Scope) -> Scope:
    """Give compiler workers only analysis authority, never operational key paths."""
    authority = scope.operator_policy
    if authority is None:
        return scope
    return scope.model_copy(
        update={
            "operator_policy": OperatorPolicy(
                schema="apizr.operator-policy/v1",
                grants=tuple(
                    g for g in authority.grants if isinstance(g, AnalysisGrant)
                ),
            )
        }
    )


class DeliverySession(Model):
    request: BatchRequest
    plugins_dir: str
    _directory = field_validator("plugins_dir")(Docker.absolute.__func__)


class McpSession(Model):
    analysis: Scope
    delivery: DeliverySession | None = None

    @model_validator(mode="after")
    def delivery_requires_authority(self):
        if self.delivery is not None and self.analysis.operator_policy is None:
            raise ValueError("delivery_policy_required")
        return self


def load_delivery_request(path: Path) -> BatchRequest:
    """Read the selected regular file once, refusing redirected/bounded JSON."""
    if not path.is_absolute():
        raise ValueError("absolute_delivery_request_required")
    raw = read_regular(path, MAX_DELIVERY_REQUEST_BYTES)
    json.loads(raw, object_pairs_hook=unique_object)
    return BatchRequest.model_validate_json(raw, strict=True)


def read_session(descriptor: int) -> McpSession:
    """Consume the inherited snapshot; never reopen a request or policy path."""
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("invalid_session")
        raw = stream.read(MAX_SESSION_BYTES + 1)
    if len(raw) > MAX_SESSION_BYTES:
        raise ValueError("session_too_large")
    data = json.loads(raw, object_pairs_hook=unique_object)
    # Preserve the read-only launcher wire format for already-installed plugins.
    session = (
        McpSession.model_validate_json(raw, strict=True)
        if isinstance(data, dict) and "analysis" in data
        else McpSession(analysis=Scope.model_validate_json(raw, strict=True))
    )
    check_scope(session.analysis)
    return session
