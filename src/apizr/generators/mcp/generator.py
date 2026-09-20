"""Render standalone MCP artifacts without loading the runtime SDK or source."""

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apizr.execution.policy import ExecutionPolicy
from importlib.resources import files
from pathlib import Path, PurePosixPath

from pydantic import JsonValue

from apizr.capabilities import canonical_bytes as ir_bytes
from apizr.capabilities.model import Digest
from apizr.inspection import Inspection
from apizr.interfaces.output import write_bundle
from apizr.interfaces.serialization import json_bytes
from apizr.readiness import canonical_bytes as readiness_bytes

from .model import Manifest, MCPPlan
from .planner import plan

REQUIREMENTS = b"mcp>=2.2,<3\nanyio>=4.5,<5\nuvicorn>=0.31.1,<1\n"


def tool_document(contract: MCPPlan) -> dict[str, JsonValue]:
    tools: list[JsonValue] = []
    for tool in contract.tools:
        entry: dict[str, JsonValue] = {
            "name": tool.tool_name,
            "inputSchema": tool.input_schema,
            "_meta": {"sh.outerspace.apizr/capability-id": tool.capability_id},
        }
        if tool.description is not None:
            entry["description"] = tool.description
        tools.append(entry)
    return {
        "schema_version": "apizr.mcp/v1",
        "protocol": {"target": contract.protocol.target},
        "tools": tools,
    }


def render(
    inspection: Inspection,
    source: bytes,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
    execution_policy: "ExecutionPolicy | None" = None,
) -> dict[str, bytes]:
    contract = plan(inspection, source, executable=executable, select=select)
    executable = source if contract.source.kind == "python" else executable
    if executable is None:
        raise ValueError("Notebook executable bytes are required")
    runtime = (
        files("apizr.generators.mcp").joinpath("runtime.py").read_text(encoding="utf-8")
    )
    runtime = runtime.replace(
        "from apizr.interfaces.runtime import (", "from apizr_runtime import ("
    )
    artifacts = {
        "server.py": runtime.encode("utf-8"),
        "apizr_runtime.py": files("apizr.interfaces")
        .joinpath("runtime.py")
        .read_bytes(),
        contract.executable_path: executable,
        "capability-ir.json": ir_bytes(inspection.capability_ir),
        "readiness.json": readiness_bytes(inspection.readiness),
        "mcp-tools.json": json_bytes(tool_document(contract)),
        "requirements.txt": REQUIREMENTS,
    }
    for parent in PurePosixPath(contract.executable_path).parents:
        if parent.as_posix() not in (".", "source"):
            artifacts.setdefault(parent.as_posix() + "/__init__.py", b"")
    if contract.source.kind == "notebook":
        artifacts["notebook.ipynb"] = source
    manifest = Manifest(
        **contract.model_dump(),
        artifacts={
            name: Digest.of_bytes(content)
            for name, content in sorted(artifacts.items())
        },
    )
    artifacts["apizr-mcp.json"] = json_bytes(manifest.model_dump(mode="json"))
    if execution_policy is not None:
        from apizr.governed.embedding import govern

        return govern(
            artifacts, inspection, source, executable, execution_policy, "mcp"
        )
    return dict(sorted(artifacts.items()))


def generate(
    inspection: Inspection,
    source: bytes,
    output: str | Path,
    *,
    executable: bytes | None = None,
    select: Sequence[str] | None = None,
    execution_policy: "ExecutionPolicy | None" = None,
) -> tuple[str, ...]:
    artifacts = render(
        inspection,
        source,
        executable=executable,
        select=select,
        execution_policy=execution_policy,
    )
    write_bundle(output, artifacts)
    return tuple(artifacts)
