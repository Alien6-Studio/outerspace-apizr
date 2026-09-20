# Generate an MCP server

`apizr generate mcp` exposes readiness-approved functions as Tools for MCP clients.
It consumes the same static capability and input contracts as REST generation.
It does not execute your source while generating files.

## Inspect and generate

Given `pricing.py`:

```python
from typing import Literal


def calculate(prices: list[float], /, *, currency: Literal["EUR", "USD"] = "EUR"):
    """Add the supplied prices and retain their currency."""
    return {"total": sum(prices), "currency": currency}
```

Inspect its eligibility, then generate into a new directory:

```bash
apizr inspect pricing.py
apizr generate mcp pricing.py --output-dir ./generated-mcp
```

One `.ipynb` input works too. Dotted logical identities and selection are explicit:

```bash
apizr generate mcp pricing.py --module-name project.pricing \
  --select calculate --output-dir ./generated-mcp
```

Selection accepts comma-separated names or full capability IDs. Unknown names and
non-eligible selections fail. Without selection, any conditional, unsupported or
ambiguous callable declaration prevents generation. There is no unsafe override.
Use an empty physical directory without symlink components; existing user files
are never overwritten.

## Run trusted source

Starting the generated server **imports and executes the bundled source**. Run
only source and dependencies you trust. Readiness is not a security sandbox or an
execution approval.

```bash
cd generated-mcp
uv venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python server.py --transport stdio
```

For a local HTTP endpoint instead:

```bash
.venv/bin/python server.py --transport streamable-http --port 8000
```

Connect to `http://127.0.0.1:8000/mcp`. Both transports use the official Python MCP
SDK v2 and target protocol `2026-07-28`. The same generated files serve both. The
server binds locally by default; exposing it remotely requires your deployment's
access-control policy.

The runtime environment needs no Apizr installation. `requirements.txt` declares
`mcp>=2.2,<3`, AnyIO and Uvicorn. Source dependencies are not inferred or bundled.

## Call a Tool with the official SDK

With the HTTP server running, use the official SDK client in another process:

```python
import asyncio

from mcp import Client


async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        print((await client.list_tools()).tools)
        result = await client.call_tool("calculate", {"prices": [10, 20]})
        print(result.structured_content)  # {"total": 30.0, "currency": "EUR"}


asyncio.run(main())
```

The omitted currency uses Python's default. Explicit null is accepted only for
nullable or unconstrained inputs. Extra fields and invalid types return a Tool
error. Positional-only inputs remain object fields in MCP; the adapter reconstructs
the Python call. Supplying a later optional positional-only field requires its
preceding positional-only fields, exactly as in REST.

Sync and async functions work. Results must be finite JSON-compatible values;
declared return annotations do not constrain them. Unsupported results and
unexpected exceptions produce `Tool execution failed` without internal exception
details. The server does not assign safety annotations because effects are unknown.

## Inspect the generated files

`mcp-tools.json` records the Tool names, input schemas, descriptions and original
capability IDs without starting a server. Simple ASCII function names are preserved;
long, Unicode or reserved names receive a deterministic name documented in the
[architecture reference](../../architecture/mcp-generator-v1.md#tool-identity-and-descriptions).

`apizr-mcp.json` records `apizr.mcp/v1`, protocol assumptions, source/IR/readiness
digests and artifact hashes. Source integrity is checked before runtime import,
and callable shape is checked afterwards. A modified source fails startup; rerun
generation from the intended source instead of editing its expected digest.

Only Tools are generated. Resources, Prompts, Tasks, Apps, Skills, agents,
repository scanning, containers, sandboxing and attestation are outside this path.
Historical generation and `apizr generate rest` remain available separately.

See the [MCP architecture contract](../../architecture/mcp-generator-v1.md) and
[REST guide](rest.md) for the shared validation semantics.
