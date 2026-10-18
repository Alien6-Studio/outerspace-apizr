import asyncio, json, sys
from pathlib import Path
from mcp import Client, StdioServerParameters

async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path("mcp/server.py").resolve()), "--transport", "stdio"],
    )
    async with Client(server) as client:
        if sys.argv[1] == "list":
            print("tools:", sorted(t.name for t in (await client.list_tools()).tools))
            return
        calls = {
            "red": ("rgb_to_hsv", {"red": 255, "green": 0, "blue": 0}),
            "green": ("hsv_to_rgb", {"hue": 120, "saturation": 1, "value": 1}),
            "invalid": ("rgb_to_hsv", {"red": "red", "green": 0, "blue": 0}),
        }
        name, arguments = calls[sys.argv[1]]
        result = await client.call_tool(name, arguments)
        print("is_error:", result.is_error)
        print("structured_content:", json.dumps(result.structured_content))
        if result.is_error:
            print("message:", "; ".join(c.text for c in result.content if hasattr(c, "text")))

asyncio.run(main())
