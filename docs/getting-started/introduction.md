---
title: The full journey
description: Choose Python functions, create a service and call them through REST or an AI assistant.
---

# The full journey


<span id="start-here"></span>

<span id="introduction"></span>

Apizr lets an application or an AI assistant call functions from your Python
project. You choose the functions. Apizr creates either a REST service, called
over HTTP, or an MCP server, called by a compatible AI client.

The example below creates a small shop service with two operations: calculate a
price and check stock. The helper functions stay private.

For the shortest path to a working server, follow the [Quickstart](quickstart.md).
For a research project with unfinished experiments, see
[exposing an independent serving function](user-guide/exposure.md#work-with-unfinished-research-code)
in the upcoming 0.4.5 release.

## Install

Follow [Install Apizr](install.md), then check `apizr --version` in that environment.
The current published version is 0.4.4. You will install the generated server's
dependencies when you are ready to run it.

## Walk through a small repository

Create these three files in an empty directory. `pricing.py` calculates a price,
`inventory.py` checks stock, and `api.py` provides the price operation you will
make public. You can also find them in `examples/repository-shop`.

**pricing.py**

```python
def total(unit_price: float, quantity: int = 1) -> float:
    return unit_price * quantity
```

**inventory.py**

```python
def available(stock: int, requested: int = 1) -> bool:
    return stock >= requested
```

**api.py**

```python
def quote(unit_price: float, quantity: int = 1) -> float:
    return _price(unit_price, quantity)


def _price(unit_price: float, quantity: int) -> float:
    from pricing import total

    return total(unit_price, quantity)
```

Create two small configuration files. The first tells Apizr that this example
will run in the server's Python process. Save it as `readiness-direct.json`:

```json
{"execution":{"modes":["direct"]}}
```

The second chooses the two public functions and requests REST and MCP.
Save it as `exposure-direct.json`:

```json
{"selection":{"include":["python:api:quote","python:inventory:available"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}
```

Apizr also needs permission to read your project. Run this command in the same
directory to create `operator.json` for that directory:

<!-- journey:authorization -->
```sh
python - <<'PYTHON'
import json
from pathlib import Path
root = str(Path.cwd().resolve())
Path("operator.json").write_text(json.dumps({
    "schema": "apizr.operator-policy/v1",
    "grants": [{"adapter": "repository", "operation": "analyze",
                "target": {"kind": "local", "root": root},
                "permissions": ["source.analyze"]}],
}))
PYTHON
```

You can now create the service. If you want to see what Apizr finds first,
the following checks are optional:

<details markdown="1">
<summary>Inspect the project before generating the service</summary>

```sh
apizr scan . --operator-policy operator.json --exclude-dir .output
apizr graph . --operator-policy operator.json --exclude-dir .output
apizr readiness . --operator-policy operator.json --exclude-dir .output --policy readiness-direct.json
apizr expose plan . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json
```

</details>

Create the REST and MCP servers:

```sh
apizr expose build rest . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/rest
apizr expose build mcp . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/mcp
```

`--exclude-dir .output` keeps generated files out of your project's analysis.
Only `api.quote` and `inventory.available` are public. The generated service
includes the pricing helper so it can calculate the result, but clients cannot
call that helper directly.

Serve the direct REST bundle:

```sh
python3 -m venv .output/runtime
.output/runtime/bin/python -m pip install -r .output/rest/requirements.txt
.output/runtime/bin/uvicorn app:app --app-dir .output/rest --host 127.0.0.1 --port 8000
```

POST `{"unit_price":12.5,"quantity":2}` to `/capabilities/api.quote` → `25.0`.
POST `{"stock":10,"requested":3}` to `/capabilities/inventory.available` → `true`.
For MCP, the generated server offers the same two operations. Follow the
[MCP client steps](quickstart.md#connect-a-client-and-make-two-calls) with
`.output/mcp` as your server directory.

## Understand the decisions

Apizr checks your code before generating a server. A function marked `READY`
can still stay private: your selection determines what clients can call.

You may see `_price` marked `CONDITIONAL` when scanning this example because it
imports code from another file. In the upcoming 0.4.5 release, the next readiness
step recognizes that local helper and succeeds. Published 0.4.4 still reports it
as conditional. The two selected public functions can be built in both versions.
See [Repository readiness](user-guide/repository-readiness.md) for diagnostic details.

Running the generated server executes your Python code with your user permissions.
Use code you trust. This example runs calls in the server process; if you need a
fresh process or container for each call, see
[execution options](../architecture/governed-repository-runtime.md).

## Choose your next step

| Task | Guide |
| --- | --- |
| Try a working service | [Quickstart](quickstart.md) |
| Choose functions from your own project | [Selection and private helpers](user-guide/exposure.md) |
| Work with one Python file | [REST](user-guide/rest.md) / [MCP](user-guide/mcp.md) |
| Understand a refused function | [Repository readiness](user-guide/repository-readiness.md) |
| Work with notebooks | [Notebook guide](../modules/notebook-transformr.md) |

## Compatibility and limits

This workflow exposes top-level Python functions. If your application needs
extra libraries or data files, prepare those in the server environment yourself.
Apizr does not deploy the service for you. Use a fresh output directory when
generating it again.
