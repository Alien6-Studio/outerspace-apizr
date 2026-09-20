"""Graph relationship semantics are versioned independently of scan/readiness."""

from typing import Literal

from pydantic import Field

from apizr.capabilities.types import ValueModel


class GraphPolicy(ValueModel):
    schema_version: Literal["apizr.graph-policy/v1"] = "apizr.graph-policy/v1"
    max_ast_nodes: int = Field(default=500000, ge=1, le=2000000)
    max_relationships: int = Field(default=50000, ge=1, le=200000)
    max_calls: int = Field(default=50000, ge=1, le=200000)
    max_imports: int = Field(default=10000, ge=1, le=100000)
