---
title: Start here
description: Install Apizr and discover, inspect and expose a small Python project through REST or MCP without Docker.
---

# Start here

<span id="introduction"></span>

Apizr is an open-source capability compiler for Python codebases. Start by
understanding your code's contracts and relationships, then choose an interface
and an execution policy.

## Install

Use Python **3.11–3.14**:

```sh
python -m pip install outerspace-apizr
apizr --version
```

For a uv-managed project, use `uv add outerspace-apizr` and prefix commands with
`uv run`. This guide describes 0.2.0. To work on Apizr itself, follow the
[development setup](developer-guide/setup.md).

## Try a small project

Save this as `example.py` in an empty directory:

```python
def subtotal(prices: list[float]) -> float:
    return sum(prices)


def total(prices: list[float], tax: float = 0.2) -> float:
    return subtotal(prices) * (1 + tax)
```

```sh
apizr scan .
apizr graph .
apizr inspect example.py
apizr readiness .
apizr generate rest example.py --select total --output-dir .output/rest
apizr generate mcp example.py --select total --output-dir .output/mcp
```

You have inventoried two functions, found the call from `total` to `subtotal`,
inspected their typed contracts and generated two interfaces for `total`.
These commands do not import or execute your input. Use a fresh output directory
when regenerating. No Docker is required.

## Choose your next step

| Task | Guide |
| --- | --- |
| Inventory a repository | [Scanner and catalog](user-guide/scan.md) |
| Understand relationships | [Capability graph](user-guide/graph.md) |
| Inspect one script or notebook | [Static inspection](user-guide/inspect.md) |
| Assess exposure evidence under a policy | [Repository readiness](user-guide/repository-readiness.md) |
| Serve an HTTP interface | [REST generation and runtime](user-guide/rest.md) |
| Expose tools to an MCP client | [MCP generation and runtime](user-guide/mcp.md) |
| Invoke trusted code under explicit limits | [Governed local and OCI execution](user-guide/execute.md) |
| Generate a notebook/script API and container | [Legacy pipeline](user-guide/apizr.md) |
| Check supported environments and compatibility | [Compatibility notes](developer-guide/releases.md) |

Starting a direct generated server imports and executes the source module.
`READY` describes static contract eligibility, not runtime safety. Governed
execution is experimental; local processes do not isolate host filesystem or
network access. See the [architecture overview](../architecture/overview.md)
for the separation between discovery, interfaces and execution.
