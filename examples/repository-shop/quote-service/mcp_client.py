"""Initialize and call a real generated MCP service, with deterministic assertions."""

import json
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters


async def main():
    async with Client(
        StdioServerParameters(command=sys.argv[1], args=[sys.argv[2]]),
        read_timeout_seconds=20,
    ) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["api.quote"]
        result = await client.call_tool(
            "api.quote", json.loads(Path(sys.argv[3]).read_text())
        )
        assert not result.is_error
        assert result.structured_content["total_cents"] == 9180
        print(json.dumps(result.structured_content, sort_keys=True))
        invalid = await client.call_tool(
            "api.quote", {"order": {"lines": [], "coupon": "none", "extra": True}}
        )
        assert invalid.is_error
        print("Extra input field refused")
        stock = await client.call_tool(
            "api.quote",
            {
                "order": {
                    "lines": [{"sku": "DESK-LAMP", "quantity": 13}],
                    "coupon": "none",
                }
            },
        )
        assert not stock.is_error
        assert stock.structured_content == {"ok": False, "reason": "insufficient_stock"}
        print("Insufficient stock returned as a business refusal")


anyio.run(main)
