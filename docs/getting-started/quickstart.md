---
title: Quickstart
description: Generate MCP and REST interfaces from the versioned repository-shop example and verify your first calls.
---

# Make your first MCP and REST calls

Expose only `python:api:quote` and `python:inventory:available` from
[`examples/repository-shop`](https://github.com/Alien6-Studio/outerspace-apizr/tree/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop).
For `quote(unit_price=12.5, quantity=2)` and `available(stock=10, requested=3)`,
REST returns `25.0` and `true`; MCP returns `{"result": 25.0}` and `{"result": true}`.

Complete the shared preparation, then choose **[MCP](#use-mcp)** or
**[REST](#use-rest-instead)**. Within MCP, your usual client and the Python test
are alternatives. No plugin, Docker or AI account is needed for the Python path.

## Prepare an isolated workspace

**Goal:** use Apizr and keep generated runtime dependencies separate.
Complete [Install Apizr](install.md), choosing
pip in `core/` and activating it. You need Python 3.11–3.14, `venv`, pip, `curl`,
a POSIX shell on a qualified macOS/Linux target and network access for the
versioned example and declared server requirements. Keep the same terminal.
From a writable parent directory, use a new workspace:

<!-- quickstart:setup -->
```sh
mkdir apizr-quickstart
cd apizr-quickstart
apizr --version
python3 -m venv runtime
```

**Observe:** the package reports `0.4.1`. `runtime/` is a separate environment for the
generated servers and test client; installing their requirements will not alter
the compiler environment. No source checkout is needed.

## Get the example and choose its public functions

**Goal:** fetch all three source files from an existing, recorded commit, rather than copying
an unversioned example from `master`.

<!-- quickstart:sources -->
```sh
mkdir shop
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/api.py --output shop/api.py
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/inventory.py --output shop/inventory.py
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/pricing.py --output shop/pricing.py
ls shop
```

**Observe:** `api.py`, `inventory.py` and `pricing.py` are present. `api.quote`
uses a private helper and `pricing.total`; only the two functions you select next
will be public.

**Readiness** assesses whether the code evidence supports an interface. Its policy
below permits the direct execution mode. An **exposure policy** names the public
functions, interfaces and allowed modes. Create the two policies and an **operator policy**: the latter authorizes analysis
of only this example’s canonical root, without granting execution or publication:

<!-- quickstart:policies -->
```sh
cat > readiness-direct.json <<'JSON'
{"execution":{"modes":["direct"]}}
JSON
cat > exposure-direct.json <<'JSON'
{"selection":{"include":["python:api:quote","python:inventory:available"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}
JSON
python - <<'PYTHON'
import json
from pathlib import Path
root = str(Path("shop").resolve(strict=True))
policy = {
    "schema": "apizr.operator-policy/v1",
    "grants": [{
        "adapter": "repository",
        "operation": "analyze",
        "target": {"kind": "local", "root": root},
        "permissions": ["source.analyze"],
    }],
}
Path("operator.json").write_text(json.dumps(policy, indent=2) + "\n")
print("Authorized source:", root)
PYTHON
```

**Observe:** the three policy files exist beside `shop`, not inside it. Only
`python:api:quote` and `python:inventory:available` are selected.
Keep `shop` at that path. If you move it or use `apizr.toml`, explicitly regenerate
the grant for the actual configured root; a project file does not grant access. Being ready does
not automatically expose a function.

## Choose your interface

The workspace, sources and policies above are shared. Continue with **one** path:

[Use MCP](#use-mcp){ .md-button .md-button--primary }
[Use REST](#use-rest-instead){ .md-button }

- **MCP:** generate tools, then connect your usual client **or** test them with Python.
- **REST:** generate an HTTP API and send two requests with curl. Skip the MCP sections.

## Use MCP

### Generate the MCP bundle

**Goal:** turn the selected functions into callable MCP tools. A **bundle** is the
generated server, its contracts and the source it needs.

<!-- quickstart:generate-mcp -->
```sh
apizr expose build mcp shop --operator-policy operator.json --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir build/mcp
```

**Observe:** generation succeeds and `build/mcp` contains `server.py`,
`mcp-tools.json`, `requirements.txt` and supporting artifacts. The tools are named
`api.quote` and `inventory.available`. Helpers are packaged as support, not tools.
Use a fresh output directory when generating again; do not edit generated files
to bypass their integrity checks.

`expose build` performs the required scan, readiness assessment and exposure plan.
Separate `scan`, `graph`, `readiness` and `expose plan` commands are optional ways
to inspect these stages, not prerequisites. Generation does **not** execute the
project. A conditional private helper does not prevent these two selected public
functions from being generated.

### Connect a client and make two calls

**Goal:** complete a real MCP exchange, not just start a process. Install the
bundle's declared runtime dependencies into the separate runtime environment:

<!-- quickstart:install-mcp -->
```sh
runtime/bin/python -m pip install -r build/mcp/requirements.txt
```

**Observe:** the MCP SDK and server requirements install successfully. Both client
choices below use this same bundle and environment. Choose **one**; running the
Python example is not required before connecting your usual client.

!!! warning "Calls execute trusted Python"
    This example uses **direct** mode: the functions execute inside the generated
    server with your user permissions. Analyze unfamiliar code before trusting it.
    A readiness result is not a security approval. For governed execution, an
    **execution policy** chooses a worker backend and its required limits; see
    [the full journey](introduction.md#understand-the-decisions).

This is a **generated business-function MCP server**. It is distinct from the
[Apizr analysis MCP server](../reference/apizr-mcp-server.md),
which inspects repositories and plans exposure without executing their functions.

<details id="connect-an-ai-client" markdown="1">
<summary>With your usual client</summary>

On macOS, for example, the [official local-server guide for Claude Desktop](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
documents **Settings → Developer → Edit Config**, the `mcpServers` structure,
absolute paths and a full restart after saving. Install Claude Desktop separately
if you choose this client; the optional Python test does not require it.

Run `pwd` in `apizr-quickstart` to obtain its absolute path. Add this entry to the
existing `mcpServers` object, preserving any other servers. Replace both
`/absolute/path/apizr-quickstart` prefixes with that real path; do not use `~` or
shell variables in this JSON:

```json
{
  "mcpServers": {
    "repository-shop": {
      "command": "/absolute/path/apizr-quickstart/runtime/bin/python",
      "args": [
        "/absolute/path/apizr-quickstart/build/mcp/server.py",
        "--transport",
        "stdio"
      ]
    }
  }
}
```

After restarting the client, inspect the server's available tools. Ask it to call
`api.quote` with `unit_price=12.5, quantity=2`, then `inventory.available` with
`stock=10, requested=3`. Approve only those intended calls and inspect the tool
results (`{"result": 25.0}` and `{"result": true}` from this generated bundle),
not just the assistant's prose answer.

This configuration follows the official client documentation. Apizr's documented
automated proof uses the Python client in the other choice; it does not claim a graphical
Claude Desktop session was exercised. Other MCP clients can use the same stdio
command and arguments according to their own configuration format.

</details>

<details id="test-with-python" markdown="1">
<summary>Test with Python — no AI account</summary>

This bundle uses the SDK's v2 client API; follow the
[official Python client documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)
and [stdio transport configuration](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md).
The small client below starts the generated server with that same Python, completes
the protocol handshake, lists its tools and calls them. No AI account is required.

Run this from `apizr-quickstart` using its runtime Python:

<!-- quickstart:client -->
```sh
runtime/bin/python - <<'PY'
import asyncio
import json
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


async def main():
    server = StdioServerParameters(
        command=sys.executable,
        args=[str(Path("build/mcp/server.py").resolve()), "--transport", "stdio"],
    )
    async with Client(server, read_timeout_seconds=10) as client:
        names = sorted(tool.name for tool in (await client.list_tools()).tools)
        assert names == ["api.quote", "inventory.available"], names
        print("tools:", ", ".join(names))
        quote = await client.call_tool("api.quote", {"unit_price": 12.5, "quantity": 2})
        available = await client.call_tool("inventory.available", {"stock": 10, "requested": 3})
        assert not quote.is_error and not available.is_error
        assert quote.structured_content == {"result": 25.0}
        assert available.structured_content == {"result": True}
        print("quote:", json.dumps(quote.structured_content))
        print("available:", json.dumps(available.structured_content))


asyncio.run(main())
PY
```

**Observe:** the client prints these results, then closes the server connection:

```text
tools: api.quote, inventory.available
quote: {"result": 25.0}
available: {"result": true}
```

The server may also log diagnostic messages to stderr. Running
`python build/mcp/server.py --transport stdio` alone waits for an MCP client;
it is not evidence that any tool has been called. Do not type chat messages into
its protocol stream.

</details>

After your two successful calls, [continue with your own code](#continue-with-your-own-code).
You can finish here without following the REST path.

## Use REST {#use-rest-instead}

**Goal:** expose the same two functions as HTTP endpoints. After the workspace,
source and policy steps, you can choose REST directly; the MCP steps are not
required. Keep the compiler environment active and run:

<!-- quickstart:generate-rest -->
```sh
apizr expose build rest shop --operator-policy operator.json --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir build/rest
runtime/bin/python -m pip install -r build/rest/requirements.txt
```

**Observe:** `build/rest` contains `app.py`, `openapi.json`, `requirements.txt` and
supporting artifacts. Starting this server executes trusted source inside its
process with your user permissions (**direct** mode). Readiness is not a security
approval. For governed workers and their limits, see
[execution policies](introduction.md#understand-the-decisions).
Use an available local port; this example
uses 8000 and binds only to your machine:

<!-- quickstart:serve-rest -->
```sh
runtime/bin/uvicorn app:app --app-dir build/rest --host 127.0.0.1 --port 8000
```

**Observe:** Uvicorn reports that the server is running. Keep that terminal open.
In a second terminal with `curl` available, send the two requests:

<!-- quickstart:call-rest -->
```sh
curl --fail --silent --show-error http://127.0.0.1:8000/capabilities/api.quote --header 'Content-Type: application/json' --data '{"unit_price":12.5,"quantity":2}'
curl --fail --silent --show-error http://127.0.0.1:8000/capabilities/inventory.available --header 'Content-Type: application/json' --data '{"stock":10,"requested":3}'
```

**Observe:** the response bodies are `25.0` and `true` respectively (curl does not
append a newline). Open `http://127.0.0.1:8000/docs` for the generated API contract.
Stop the server with Ctrl+C in its terminal when finished.

## Continue with your own code

Follow [The full journey](introduction.md) to inspect each compiler stage, understand
policy decisions and choose direct or governed execution. For your own repository,
replace `shop` with its local source root and explicitly choose its capability IDs
in your exposure policy. Prepare a new operator grant for that exact root, then use
`apizr scan /path/to/source --operator-policy your-operator.json` to discover those IDs;
review the source and application dependencies before executing a generated bundle.
The [exposure guide](user-guide/exposure.md) covers refusals and worker policies.
