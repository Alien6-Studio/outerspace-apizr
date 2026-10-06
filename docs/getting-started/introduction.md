---
title: The full journey
description: Discover, understand, assess, select, expose and execute a Python repository through REST or MCP.
---

# The full journey


<span id="start-here"></span>

<span id="introduction"></span>

Use this guide to understand how Apizr turns a Python project into a service:
find its functions, choose which ones to expose, generate an interface and run it.

For a first working server and verified calls, start with the [Quickstart](quickstart.md).
This page explains the separate stages and their diagnostic outputs.

## Install

Follow [Install Apizr](install.md), then activate the core environment and check
`apizr --version`. These guides use Apizr 0.4 and Python 3.11–3.14.

The minimal core handles static Python analysis and generation. Generated servers
have their own requirements; the [Quickstart](quickstart.md) installs them in a
separate runtime environment. Optional analysis and delivery plugins are installed
through [plugin profiles](install.md#choose-a-plugin-profile).
For notebook or historical pipeline dependencies, see [development setup](developer-guide/setup.md).

## Walk through a small repository

Create these three files in an empty directory (also available in the repository's
`examples/repository-shop`):

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

Save `readiness-direct.json`:

```json
{"execution":{"modes":["direct"]}}
```

Save `exposure-direct.json`:

```json
{"selection":{"include":["python:api:quote","python:inventory:available"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}
```

**Readiness** assesses whether code evidence supports an interface. The
**exposure policy** selects the public functions and allowed modes. A **bundle**
is the generated server, its contracts and the supporting source.

Save an **operator policy** for this directory before reading its source. This
allows analysis only; readiness, exposure and execution policies stay independent.

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

`expose build` performs the analysis and generates your service in one command.
The first four commands below let you inspect the intermediate results when
you need to understand a selection or diagnose a refusal:

```sh
apizr scan . --operator-policy operator.json --exclude-dir .output
apizr graph . --operator-policy operator.json --exclude-dir .output
apizr readiness . --operator-policy operator.json --exclude-dir .output --policy readiness-direct.json
apizr expose plan . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json
apizr expose build rest . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/rest
apizr expose build mcp . --operator-policy operator.json --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/mcp
```

The explicit `.output` exclusion keeps generated files outside the scan universe.
Scan reports three ready functions and one conditional support helper. In the
upcoming 0.4.5 release, repository Readiness resolves that helper's local import:
all four repository assessments are ready and its exit code is 0. The helper's
original local assessment stays conditional. Published 0.4.4 keeps three ready
repository assessments and one conditional helper, with readiness exit code 1.
The two explicitly selected public functions are eligible in both versions;
planning and building succeed. **READY does not mean exposed.** `pricing.total`
is packaged and called through `api._price`, but neither helper is public.

Serve the direct REST bundle:

```sh
python3 -m venv .output/runtime
.output/runtime/bin/python -m pip install -r .output/rest/requirements.txt
.output/runtime/bin/uvicorn app:app --app-dir .output/rest --host 127.0.0.1 --port 8000
```

POST `{"unit_price":12.5,"quantity":2}` to `/capabilities/api.quote` → `25.0`.
POST `{"stock":10,"requested":3}` to `/capabilities/inventory.available` → `true`.
The separate runtime environment keeps server dependencies out of Apizr's core.
The MCP bundle exposes the same two names; follow the
[MCP client steps](quickstart.md#connect-a-client-and-make-two-calls) with
`.output/mcp` as your bundle directory. These servers execute trusted code.
Use a fresh output directory when regenerating.

## Understand the decisions

| Layer | Responsibility |
| --- | --- |
| Repository Readiness policy | Assess evidence and compatible execution contracts |
| Exposure policy | Explicitly select public capability IDs, interfaces and allowed modes |
| Execution policy | Configure the one actual worker backend and its required controls |

**READY does not mean exposed.** The graph describes relationships; it does not
publish their targets. Here `api.quote` calls private support code in `pricing.py`.
Only `api.quote` and `inventory.available` appear in REST/MCP.

## Choose your next step

| Task | Guide |
| --- | --- |
| Inventory a repository | [Scanner and catalog](user-guide/scan.md) |
| Understand relationships | [Capability graph](user-guide/graph.md) |
| Inspect one script or notebook | [Static inspection](user-guide/inspect.md) |
| Assess eligibility | [Repository readiness](user-guide/repository-readiness.md) |
| Select and expose a repository | [Exposure and policy examples](user-guide/exposure.md) |
| Use fresh local/OCI workers | [Governed repository execution](../architecture/governed-repository-runtime.md) |
| Keep single-source workflows | [REST](user-guide/rest.md) / [MCP](user-guide/mcp.md) |
| Use the historical notebook/script pipeline | [Legacy guide](user-guide/apizr.md) |

Direct state persists in the transport interpreter. Governed local state resets in
a fresh process per call; governed OCI state resets in a fresh container per call.
Local execution provides bounds/environment/cleanup, not filesystem or network
isolation. OCI uses reviewed container controls and offers an optional
[strict subprocess-deny profile](../architecture/subprocess-deny.md); it is not a VM. Both require trusted source and dependencies; neither is an automatic
untrusted-code guarantee. [Architecture and boundaries](../architecture/overview.md).

## Compatibility and limits

Modern single-source `inspect`, `generate rest/mcp` and `execute` commands remain
supported alongside repository workflows. They are not the legacy pipeline.
The historical `apizr --script` / `--notebook` pipeline is a separate path; there
is no automatic migration or publication.

Public capabilities remain top-level functions. Class/method exposure and an
enterprise control plane are not supported. Repository bundles do not infer
or install application dependencies or package arbitrary repository data files.
The [legacy pipeline](user-guide/apizr.md) supports explicit requirements and
resources, configured notebook cell selection, explicit image builds and installed
pipeline plugins. It inventories classes and methods separately and refuses
ambiguous selected definitions/overloads. See the
[notebook configuration guide](../modules/notebook-transformr.md).

Static readiness/exposure v1 adapters keep their original control vocabulary;
the strict OCI profile is selected through an **execution policy**, which chooses
the actual worker backend and its required controls. See
[compatibility notes](developer-guide/releases.md).
