"""A tool client executes the route calculation; no assistant account is needed."""

import sys

import anyio
from mcp import Client, StdioServerParameters


async def main():
    async with Client(
        StdioServerParameters(command=sys.argv[1], args=[sys.argv[2]]),
        read_timeout_seconds=20,
    ) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["plan_route"]
        result = await client.call_tool(
            "plan_route", {"stops": ["museum", "cafe", "library"]}
        )
        assert not result.is_error
        expected = {
            "ok": True,
            "route": ["warehouse", "library", "cafe", "museum", "warehouse"],
            "estimated_minutes": 12,
        }
        assert result.structured_content == expected
        print(result.structured_content)
        refused = await client.call_tool("plan_route", {"stops": ["unknown"]})
        assert refused.structured_content == {"ok": False, "reason": "unknown_stop"}
        print(refused.structured_content)


anyio.run(main)
