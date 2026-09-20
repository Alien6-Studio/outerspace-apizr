"""MCP artifact policy independent of upstream IR, readiness and REST."""

from typing import Literal

from pydantic import JsonValue

from apizr.capabilities.model import Digest
from apizr.capabilities.types import ValueModel
from apizr.interfaces.model import InvocationContract
from apizr.interfaces.planner import BoundSource


class Protocol(ValueModel):
    target: Literal["2026-07-28"] = "2026-07-28"
    sdk: Literal["mcp>=2.2,<3"] = "mcp>=2.2,<3"


class ToolContract(InvocationContract):
    tool_name: str
    input_schema: dict[str, JsonValue]


class MCPPlan(BoundSource):
    schema_version: Literal["apizr.mcp/v1"] = "apizr.mcp/v1"
    protocol: Protocol = Protocol()
    tools: tuple[ToolContract, ...]


class Manifest(MCPPlan):
    artifacts: dict[str, Digest]
