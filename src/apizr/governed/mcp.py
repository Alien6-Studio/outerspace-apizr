"""MCP SDK transport mapping; execution remains transport-neutral."""

import argparse
import asyncio
import json
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

from apizr.execution.protocol import finite_json

from .runtime import GovernedRuntime, artifact


def tool_error(message: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=message)], is_error=True
    )


def create_server(root: Path) -> Server[dict[str, object]]:
    runtime = GovernedRuntime(root, "mcp")
    tools = [
        Tool.model_validate(value)
        for value in json.loads(artifact(root, "mcp-tools.json"))["tools"]
    ]
    identities = {
        plan.interface.name: identity for identity, plan in runtime.plans.items()
    }

    async def list_tools(
        ctx: ServerRequestContext[dict[str, object]],
        params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        return ListToolsResult(tools=tools)

    async def call_tool(
        ctx: ServerRequestContext[dict[str, object]], params: CallToolRequestParams
    ) -> CallToolResult:
        identity = identities.get(params.name)
        if identity is None:
            return tool_error("Unknown tool")
        try:
            payload = finite_json(
                params.arguments if params.arguments is not None else {}
            )
        except (ValueError, RecursionError):
            return tool_error("Invalid tool arguments")
        result = await anyio.to_thread.run_sync(runtime.invoke, identity, payload)
        if result.status == "success":
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=json.dumps(
                            result.value,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                    )
                ],
                structured_content=result.value,
            )
        if result.status == "invalid_input":
            return tool_error("Invalid tool arguments")
        if result.status == "timeout":
            return tool_error("Tool execution timed out")
        return tool_error("Tool execution failed")

    return Server(
        "Apizr MCP",
        version="apizr.mcp/v1",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )


async def serve_stdio(server: Server[dict[str, object]]) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main(root: Path) -> None:
    parser = argparse.ArgumentParser(
        description="Run a governed trusted-code MCP bundle"
    )
    parser.add_argument(
        "--transport", choices=["stdio", "streamable-http"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = create_server(root)
    if args.transport == "stdio":
        asyncio.run(serve_stdio(server))
    else:
        uvicorn.run(
            server.streamable_http_app(host=args.host), host=args.host, port=args.port
        )
