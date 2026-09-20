"""Map shared eligible invocation contracts to deterministically named Tools."""

import re
from collections.abc import Sequence
from hashlib import sha256

from apizr.inspection import Inspection
from apizr.interfaces.planner import plan as interface_plan
from apizr.interfaces.schema import request_schema

from .model import MCPPlan, ToolContract


def tool_name(identity: str, name: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name) and not name.startswith("apizr_"):
        return name
    return "apizr_" + sha256(identity.encode("utf-8")).hexdigest()


def plan(
    inspection: Inspection,
    source: bytes,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
) -> MCPPlan:
    interface = interface_plan(inspection, source, executable=executable, select=select)
    tools = tuple(
        ToolContract(
            **c.model_dump(),
            tool_name=tool_name(c.capability_id, c.name),
            input_schema=request_schema(c),
        )
        for c in interface.capabilities
    )
    if len({t.tool_name for t in tools}) != len(tools):
        raise ValueError("MCP tool name collision")
    return MCPPlan(**interface.model_dump(exclude={"capabilities"}), tools=tools)
