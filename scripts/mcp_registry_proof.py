"""Exercise the registry command from local wheels, without publishing a package."""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

import anyio
from mcp import Client, StdioServerParameters

REPO = Path(__file__).resolve().parents[1]


async def main(root: Path):
    config = json.loads((root / "installed.json").read_text())
    descriptor = json.loads((REPO / "server.json").read_text())
    package = descriptor["packages"][0]
    assert package["runtimeHint"] == "uvx"
    assert package["transport"] == {"type": "stdio"}
    uvx = shutil.which("uvx")
    assert uvx is not None
    wheel = next((root / "wheels").glob("outerspace_apizr_mcp-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        metadata = BytesParser().parsebytes(
            archive.read(
                next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            )
        )
        assert f"<!-- mcp-name: {descriptor['name']} -->" in metadata.get_payload()
    # Substitute only the unpublished package source. Everything after the
    # executable name comes from the committed descriptor and operator inputs.
    prefix = [
        "--isolated",
        "--offline",
        "--no-index",
        "--find-links",
        str(root / "wheels"),
        "--python",
        str(root / "client/bin/python"),
        "--from",
        str(wheel),
        package["identifier"],
    ]
    values = {
        "--project": config["project"],
        "--operator-policy": config["operator_policy"],
        "--plugins-dir": config["store"],
    }
    arguments = []
    for argument in package["packageArguments"]:
        assert argument["type"] == "named" and argument["isRequired"]
        arguments.extend([argument["name"], values[argument["name"]]])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for mode in ("auto", "legacy"):
        async with Client(
            StdioServerParameters(command=uvx, args=prefix + arguments, env=env),
            mode=mode,
            read_timeout_seconds=30,
        ) as client:
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == {
                "apizr_analyze",
                "apizr_readiness",
                "apizr_plan_exposure",
            }
            assert all(
                tool.annotations is not None
                and tool.annotations.read_only_hint
                and tool.input_schema
                and tool.output_schema
                for tool in tools
            )
            for tool in tools:
                result = await client.call_tool(tool.name, {})
                assert not result.is_error and result.structured_content, result
    for flag, replacement, expected in (
        ("--operator-policy", None, "operator_policy_required"),
        ("--plugins-dir", str(root / "registry-absent-store"), "plugin_not_installed"),
    ):
        denied = arguments.copy()
        index = denied.index(flag)
        if replacement is None:
            del denied[index : index + 2]
        else:
            denied[index + 1] = replacement
        result = subprocess.run(
            [uvx, *prefix, *denied],
            input=b"",
            capture_output=True,
            env=env,
            timeout=30,
        )
        assert result.returncode == 2 and not result.stdout, result
        assert expected.encode() in result.stderr, result.stderr
    assert not (root / "registry-absent-store").exists()
    report = {
        "success": True,
        "source": "local development wheels, not public 0.4.3",
        "protocol_modes": ["auto", "legacy"],
        "read_only_tools": 3,
        "policy_and_installation_refusals": True,
    }
    (root / "registry-launch.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PASS registry uvx launcher, three read-only tools, policy/store refusals")


if __name__ == "__main__":
    anyio.run(main, Path(sys.argv[1]))
