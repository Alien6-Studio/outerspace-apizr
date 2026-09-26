"""Installed real SDK session retains admission after disable and across execve."""

import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters
from smoke_extension_packaging import snapshot


async def prove(root: Path) -> None:
    config = json.loads((root / "installed.json").read_text())
    observations = []

    def cli(*args: str, expected: int = 0):
        process = subprocess.run(
            [config["cli"], "plugins", *args, "--plugins-dir", config["store"]],
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert process.returncode == expected, (process.stdout, process.stderr)
        observations.append(
            {
                "command": list(args),
                "code": process.returncode,
                "stdout": process.stdout,
            }
        )
        return json.loads(process.stdout) if "--json" in args else {}

    target = StdioServerParameters(
        command=config["cli"],
        args=[
            "mcp",
            "serve",
            "--project",
            config["project"],
            "--plugins-dir",
            config["store"],
        ],
        cwd=root,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    with anyio.fail_after(60):
        async with Client(target, read_timeout_seconds=15) as client:
            assert len((await client.list_tools()).tools) == 3
            cli("disable", "apizr-mcp")
            refused = cli(
                "uninstall", "apizr-mcp", "--version", "0.0.0", "--json", expected=1
            )
            assert refused["state"] == "busy"
            # Existing admission survives disable and the rejected uninstall.
            analyzed = await client.call_tool("apizr_analyze", {})
            assert not analyzed.is_error
        removed = cli("uninstall", "apizr-mcp", "--version", "0.0.0", "--json")
        assert removed["state"] == "complete" and removed["environment_removed"]
        assert (
            cli("uninstall", "apizr-mcp", "--version", "0.0.0", "--json")["state"]
            == "absent"
        )
    assert snapshot(root / "core") == json.loads(
        (root / "core-before.json").read_text()
    )
    (root / "mcp-uninstall-evidence.json").write_text(
        json.dumps(observations, indent=2) + "\n"
    )
    print(
        "PASS real installed MCP: session active, disable, uninstall busy, call succeeds, close, uninstall complete, repeat absent"
    )


if __name__ == "__main__":
    anyio.run(prove, Path(sys.argv[1]))
