"""Standalone Tools-only MCP SDK v2 adapter. Source import is trusted execution."""

import argparse
import asyncio
import json
from functools import partial
from pathlib import Path

import anyio
import uvicorn
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
)

from apizr.interfaces.results import finite_json_value as result_value
from apizr.interfaces.results import normalize_result_for_json
from apizr.interfaces.runtime import (
    JSON,
    RuntimeInvocation,
    arguments,
)
from apizr.repository_interfaces.runtime import load_bundle


class RuntimeTool(RuntimeInvocation):
    tool_name: str
    description: str | None
    input_schema: dict[str, JSON]


def tool_error(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=message)], is_error=True
    )


def create_server(
    root: Path, expected: dict[str, str] | None = None
) -> Server[dict[str, object]]:
    plan, functions, _loader, _artifacts = load_bundle(root, "mcp", expected)
    bindings = {
        t["tool_name"]: (t, functions[t["capability_id"]]) for t in plan["tools"]
    }
    tools = [
        Tool(
            name=t["tool_name"],
            description=t["description"],
            input_schema=t["input_schema"],
            _meta={"sh.outerspace.apizr/capability-id": t["capability_id"]},
        )
        for t in plan["tools"]
    ]

    async def list_tools(
        ctx: ServerRequestContext[dict[str, object]],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=tools)

    async def call_tool(
        ctx: ServerRequestContext[dict[str, object]], params: CallToolRequestParams
    ) -> CallToolResult:
        binding = bindings.get(params.name)
        if binding is None:
            return tool_error("Unknown tool")
        contract, function = binding
        try:
            payload = result_value(
                params.arguments if params.arguments is not None else {}
            )
            args, kwargs = arguments(function, contract, payload)
        except (ValueError, RecursionError):
            return tool_error("Invalid tool arguments")
        try:
            if contract["execution"] == "async":
                result = await function(*args, **kwargs)
            else:
                result = await anyio.to_thread.run_sync(
                    partial(function, *args, **kwargs)
                )
            value = normalize_result_for_json(result)
            # MCP structuredContent must be an object on every supported protocol.
            value = value if isinstance(value, dict) else {"result": value}
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            value,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                    )
                ],
                structured_content=value,
            )
        except Exception:
            return tool_error("Tool execution failed")

    return Server(
        "Apizr MCP",
        version="apizr.repository-mcp/v1",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve_stdio(server: Server[dict[str, object]]) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(expected: dict[str, str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run a trusted Apizr MCP bundle")
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    server = create_server(root, expected)
    if args.transport == "stdio":
        asyncio.run(serve_stdio(server))
    else:
        uvicorn.run(
            server.streamable_http_app(host=args.host), host=args.host, port=args.port
        )
