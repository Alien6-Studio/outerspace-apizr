"""Execute the documented TypedDict journey with an installed CLI outside source."""

import argparse
import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import anyio
from mcp import Client, StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


def proof(cli: Path, python: Path, output: Path | None = None) -> dict:
    guide = (ROOT / "docs/getting-started/user-guide/inspect.md").read_text()
    example = re.search(
        r"<!-- typed-dict:example -->\s*```python\n(.*?)```", guide, re.S
    )
    commands = re.search(r"<!-- typed-dict:commands -->\s*```sh\n(.*?)```", guide, re.S)
    assert example and commands
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    result = {
        "cli": str(cli.resolve()),
        "server_python": str(python.absolute()),
        "commands": [],
        "rest": [],
        "mcp": [],
    }
    with tempfile.TemporaryDirectory(prefix="apizr-typed-proof-") as directory:
        root = Path(directory).resolve()
        (root / "prediction.py").write_text(example[1])
        for line in commands[1].splitlines():
            command = [str(cli.resolve()), *shlex.split(line)[1:]]
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            result["commands"].append(line)
            if "inspect" in command:
                inspection = json.loads(completed.stdout)
                assert inspection["readiness"]["assessments"][0][
                    "can_generate_interface"
                ]
                result["inspection"] = inspection
        payload = {"payload": {"customer_id": "c", "features": {"age": 2, "score": 3}}}
        invalid = [
            {"payload": {}},
            {"payload": {"customer_id": "c", "features": {"age": "2", "score": 3}}},
            {
                "payload": {
                    "customer_id": "c",
                    "features": {"age": 2, "score": 3, "extra": 1},
                }
            },
            {"payload": {**payload["payload"], "extra": 1}},
        ]
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        rest_root = root / ".output/typed-rest"
        script = "import sys; sys.path.insert(0, sys.argv[1]); from app import app; import uvicorn; assert not any(n == 'apizr' or n.startswith('apizr.') for n in sys.modules); uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[2]))"
        with (root / "rest.log").open("w+") as log:
            process = subprocess.Popen(
                [str(python.absolute()), "-I", "-c", script, str(rest_root), str(port)],
                cwd=root,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 15
                while True:
                    try:
                        with urlopen(url + "/health", timeout=1) as response:
                            assert json.load(response) == {"status": "ok"}
                        break
                    except OSError:
                        if process.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            raise AssertionError(log.read()) from None
                        time.sleep(0.05)
                for arguments in [payload, *invalid]:
                    request = Request(
                        url + "/capabilities/predict",
                        data=json.dumps(arguments).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                    try:
                        with urlopen(request, timeout=10) as response:
                            entry = {
                                "status": response.status,
                                "body": json.load(response),
                            }
                    except HTTPError as error:
                        entry = {"status": error.code, "body": json.load(error)}
                    result["rest"].append(entry)
                assert result["rest"][0] == {"status": 200, "body": 6.0}
                assert all(item["status"] == 422 for item in result["rest"][1:])
            finally:
                process.terminate()
                process.wait(timeout=10)

        async def mcp():
            async with Client(
                StdioServerParameters(
                    command=str(python.absolute()),
                    args=[str(root / ".output/typed-mcp/server.py")],
                    cwd=root,
                    env=env,
                ),
                read_timeout_seconds=10,
            ) as client:
                tool = (await client.list_tools()).tools[0]
                assert tool.output_schema is None
                result["input_schema"] = tool.input_schema
                for arguments in [payload, *invalid]:
                    call = await client.call_tool("predict", arguments)
                    assert call.content[0].type == "text"
                    result["mcp"].append(
                        {
                            "isError": call.is_error,
                            "structuredContent": call.structured_content,
                            "text": call.content[0].text,
                        }
                    )
                assert result["mcp"][0]["structuredContent"] == {"result": 6.0}
                assert not result["mcp"][0]["isError"]
                assert json.loads(result["mcp"][0]["text"]) == {"result": 6.0}
                assert all(
                    item
                    == {
                        "isError": True,
                        "structuredContent": None,
                        "text": "Invalid tool arguments",
                    }
                    for item in result["mcp"][1:]
                )

        anyio.run(mcp)
    if output:
        output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "PASS: installed documented TypedDict inspection, HTTP, official MCP stdio and nested refusals"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cli", type=Path)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    proof(args.cli, args.python, args.output)


if __name__ == "__main__":
    main()
