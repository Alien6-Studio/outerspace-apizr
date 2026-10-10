---
title: Quickstart
description: Generate your first REST API or MCP server from Python, run it locally and make two calls.
---

# Make your first MCP and REST calls

## Inspect a training script first (0.4.5 development)

If you have the development checkout installed, you can start with experiment
evidence before building a service. This example requires only Apizr's core:

<!-- experiment-inspection:quickstart -->
```sh
cat > example.py <<'PY'
from sklearn.metrics import roc_auc_score

learning_rate = 0.05
roc_auc_score(labels, predictions)
PY
apizr experiment inspect example.py
```

Parameters shows a static candidate; Metrics shows a recognized call with its value
unobserved. Undefined names and an absent sklearn installation are fine because
inspection does not execute the file. See the [experiment guide](user-guide/experiment-inspection.md)
for data fingerprints, notebooks and all eight sections.

## Run a trusted experiment (0.4.5 development)

`inspect` never executes your code. **`run` executes trusted code in a fresh
process with host filesystem, network and subprocess access. It is not a security
sandbox.** Use a complete workload with its dependencies already installed in the
same environment as Apizr. This separate example needs only the standard library:

<!-- experiment-run:quickstart -->
```sh
cat > local_run.py <<'PY'
from pathlib import Path
mean = sum([2, 4, 6]) / 3
Path("model.json").write_text('{"mean": 4.0}\n')
PY
apizr experiment inspect local_run.py
RUN=$(apizr experiment run local_run.py --metric mean=mean --output model=model.json --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment show "$RUN"
```

The Run records the actual `mean` binding and the output's byte identity. The
local store contains evidence JSON, not a copy of the model. See
[running experiments](user-guide/experiment-runs.md) for notebooks, inputs,
timeouts, failed Runs and the difference between intent and observation.

## Make a service from functions

Turn two Python functions into a local service. You will calculate a price
(`12.5 × 2 = 25.0`) and check stock (`3 ≤ 10` gives `true`).
Prepare the example once, then choose **[REST](#use-rest-instead)** or
**[MCP](#use-mcp)**. No plugin, Docker or AI account is needed for REST or the
Python MCP client.

## Prepare an isolated workspace

[Install Apizr](install.md) with the pip instructions and keep `core/` activated.
You need Python 3.11–3.14, `curl`, a POSIX shell on macOS/Linux and internet access
for the example and server dependencies. In the same terminal:

<!-- quickstart:setup -->
```sh
mkdir apizr-quickstart
cd apizr-quickstart
apizr --version
python3 -m venv runtime
```

`apizr --version` should report `outerspace-apizr 0.4.4`. The new `runtime/`
environment will hold the generated server's dependencies separately from Apizr.

## Get the example and choose its public functions

Download the three files from the
[recorded shop example](https://github.com/Alien6-Studio/outerspace-apizr/tree/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop):

<!-- quickstart:sources -->
```sh
mkdir shop
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/api.py --output shop/api.py
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/inventory.py --output shop/inventory.py
curl --fail --location https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/37259eaf0a231d747f1ae0eb2f7ce94b2a2b306f/examples/repository-shop/pricing.py --output shop/pricing.py
ls shop
```

You should have `api.py`, `inventory.py` and `pricing.py` in `shop/`.
Create the configuration that selects `api.quote` and `inventory.available`
and permits Apizr to analyze this directory:

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

The three files sit beside `shop/`. Keep that directory at the same location;
its analysis permission names this exact path.

<details markdown="1">
<summary>What do these three configuration files do?</summary>

- **Readiness:** describes the kind of interface Apizr can generate here.
- **Exposure:** selects the public functions and allows direct execution.
- **Operator:** permits source analysis of this directory. It grants neither
  execution nor publication.

Private helpers are included when needed, but do not become public functions.
For another project, review its source, select its functions and create an
operator grant for its own root.

</details>

## Choose your interface

[Use REST](#use-rest-instead){ .md-button .md-button--primary }
[Use MCP](#use-mcp){ .md-button }

Both paths use the files prepared above; choose one. Generation reads the source
without running it. The generated server uses **direct** mode: calls execute
trusted Python with your user permissions. Use [execution policies](introduction.md#understand-the-decisions)
when you need fresh workers or execution limits.

## Use REST {#use-rest-instead}

Generate the API and install its runtime dependencies:

<!-- quickstart:generate-rest -->
```sh
apizr expose build rest shop --operator-policy operator.json --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir build/rest
runtime/bin/python -m pip install -r build/rest/requirements.txt
```

`build/rest` contains `app.py`, `openapi.json` and the supporting source.
Start the server on a free local port:

<!-- quickstart:serve-rest -->
```sh
runtime/bin/uvicorn app:app --app-dir build/rest --host 127.0.0.1 --port 8000
```

Keep this terminal open. In a second terminal, call the two endpoints:

<!-- quickstart:call-rest -->
```sh
curl --fail --silent --show-error http://127.0.0.1:8000/capabilities/api.quote --header 'Content-Type: application/json' --data '{"unit_price":12.5,"quantity":2}'
curl --fail --silent --show-error http://127.0.0.1:8000/capabilities/inventory.available --header 'Content-Type: application/json' --data '{"stock":10,"requested":3}'
```

The response bodies are `25.0` and `true` (curl does not append a newline).
Open [the interactive API docs](http://127.0.0.1:8000/docs) to try other inputs.
Stop the server with Ctrl+C when finished.

You can now [continue with your own code](#continue-with-your-own-code), or try MCP
in the original terminal. For a different example, the [REST guide](user-guide/rest.md)
includes a video showing function selection, HTTP calls and input validation.

## Use MCP

### Generate the MCP bundle

Generate a server for the same two functions:

<!-- quickstart:generate-mcp -->
```sh
apizr expose build mcp shop --operator-policy operator.json --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir build/mcp
```

`build/mcp` contains `server.py`, `mcp-tools.json`, `requirements.txt` and the
supporting source. The tools are named `api.quote` and `inventory.available`.
Use a new output directory if you generate again.

This is your **business-function server**. The optional
[Apizr analysis MCP server](../reference/apizr-mcp-server.md) is a separate tool
for inspecting projects; you do not need it here.

### Connect a client and make two calls

Install the server dependencies in the runtime environment:

<!-- quickstart:install-mcp -->
```sh
runtime/bin/python -m pip install -r build/mcp/requirements.txt
```

Choose your usual MCP client **or** the Python client below.

<details id="connect-an-ai-client" markdown="1">
<summary>Connect your usual MCP client</summary>

For Claude Desktop on macOS, follow the
[official local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers).
In **Settings → Developer → Edit Config**, add this entry to your existing
`mcpServers` object. Replace both `/absolute/path/apizr-quickstart` prefixes with
the full directory path printed by `pwd`; keep your other servers.

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

Restart the client. Ask it to call `api.quote` with `unit_price=12.5, quantity=2`,
then `inventory.available` with `stock=10, requested=3`. Approve those calls and
look at the tool results: `{"result": 25.0}` and `{"result": true}`.
Other MCP clients can use the same command and arguments in their configuration.

</details>

<details id="test-with-python" markdown="1">
<summary>Use Python — no AI account required</summary>

Run this from `apizr-quickstart`. It starts the server, discovers the tools and
calls both of them using the installed MCP SDK:

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

Expected output:

```text
tools: api.quote, inventory.available
quote: {"result": 25.0}
available: {"result": true}
```

The client closes the connection when finished. The server may also write
logs to stderr. See the [official Python client documentation](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/index.md)
for more client options.

</details>

Starting `server.py --transport stdio` alone waits for an MCP client; it is not a
chat terminal. The [MCP guide](user-guide/mcp.md) includes a video of discovery,
calls and error handling with the Python client.

## Continue with your own code

[Initialize your project](onboarding.md), inspect its functions and select the
ones to expose. Review its source and dependencies before running the generated
service. Follow [The full journey](introduction.md) to understand each stage,
or the [exposure guide](user-guide/exposure.md) for repository configuration.

For the upcoming 0.4.5 release, your selected function can use statically resolvable
[private helpers in other modules](user-guide/exposure.md#use-private-helpers-from-the-same-repository)
without exposing those helpers.
