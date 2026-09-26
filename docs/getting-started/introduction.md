---
title: The full journey
description: Discover, understand, assess, select, expose and execute a Python repository through REST or MCP.
---

# The full journey

<span id="start-here"></span>

<span id="introduction"></span>

Apizr is an open-source capability compiler for Python codebases. The 0.3 journey
is **Discover → Understand → Assess → Select → Expose → Execute**.

For a first working server and verified calls, start with the [Quickstart](quickstart.md).
This page explains the separate stages and their diagnostic outputs.

## Install

**Latest published stable: 0.3.0.** Use Python 3.11–3.14 in a virtual environment:

```sh
python -m pip install outerspace-apizr==0.3.0
apizr --version
```

For Git sources, project configuration, isolated plugins and OCI/Attest delivery,
use the separate [unreleased 0.4 walkthrough](../development/0.4.md). The stable
commands on this page remain available in 0.3.0.

The base installation needs only Pydantic for static Python workflows.
Choose an extra when the workflow requires it:

| Workflow | Installation |
| --- | --- |
| Notebook inspection/generation | `python -m pip install "outerspace-apizr[notebook]==0.3.0"` |
| HTTP adapters | `python -m pip install "outerspace-apizr[http]==0.3.0"` |
| MCP adapters | `python -m pip install "outerspace-apizr[mcp]==0.3.0"` |
| Complete historical pipeline/web app | `python -m pip install "outerspace-apizr[legacy]==0.3.0"` |

Extras combine, for example `"outerspace-apizr[notebook,mcp]==0.3.0"`.
`[legacy]` retains the full 0.2.1 stack. Generated servers have their own requirements.
To work on Apizr itself, see [development setup](developer-guide/setup.md).

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

The first four commands below are optional diagnostics, useful for understanding
each stage. `expose build` already performs their required analysis and planning;
you do not need to run them separately before generation. To inspect each stage:

```sh
apizr scan . --exclude-dir .output
apizr graph . --exclude-dir .output
apizr readiness . --exclude-dir .output --policy readiness-direct.json
apizr expose plan . --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json
apizr expose build rest . --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/rest
apizr expose build mcp . --exclude-dir .output --readiness-policy readiness-direct.json --policy exposure-direct.json --output-dir .output/mcp
```

The explicit `.output` exclusion keeps generated files outside the scan universe.
Readiness reports three ready functions and one conditional support helper, so its
exit code is 1. The two explicitly selected public functions are eligible; planning
and building succeed. **READY does not mean exposed.** `pricing.total` is packaged
and called through `api._price`, but neither helper is public.

Serve the direct REST bundle:

```sh
python -m pip install -r .output/rest/requirements.txt
uvicorn app:app --app-dir .output/rest --host 127.0.0.1 --port 8000
```

POST `{"unit_price":12.5,"quantity":2}` to `/capabilities/api.quote` → `25.0`.
POST `{"stock":10,"requested":3}` to `/capabilities/inventory.available` → `true`.
The MCP bundle exposes the same two names. [Connect a client and verify calls](quickstart.md#connect-a-client-and-make-two-calls). Install its `requirements.txt`, then run
`python .output/mcp/server.py --transport stdio` or use `--transport streamable-http`.
These generated servers execute trusted code. Use a fresh output directory when
regenerating. Discovery and generation do not execute project source.

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
| Migrate from 0.2.1 | [0.3 release notes](../releases/0.3.0.md) |

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
enterprise control plane are outside stable 0.3.0. Repository bundles do not infer
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
