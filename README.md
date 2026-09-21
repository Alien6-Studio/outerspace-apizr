# OuterSpace Apizr

**Apizr is an open-source capability compiler for Python codebases.**

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/LICENSE)

It discovers executable capabilities, builds deterministic contracts and relationships,
exposes eligible capabilities through REST or MCP, and supports governed execution.
Python **3.11–3.14** · GPL-3.0-or-later · Release **0.2.0**

## What Apizr does

- **Discover:** inventory a Python repository without importing or executing its source.
- **Understand:** inspect typed capabilities, relationships and static readiness.
- **Expose:** generate REST or MCP interfaces from the same eligible contracts.
- **Govern:** execute trusted code under explicit local-process or OCI policies.

Scripts and notebooks are inputs for individual inspection and generation. Repository
scanning discovers Python files. The historical notebook-to-API workflow remains supported.

## Install

```sh
python -m pip install outerspace-apizr
```

For a uv-managed project: `uv add outerspace-apizr`. These instructions describe
0.2.0; check the installed release with `apizr --version`.

## A 30-second example

Save this as `example.py` in an empty project directory:

```python
def subtotal(prices: list[float]) -> float:
    return sum(prices)


def total(prices: list[float], tax: float = 0.2) -> float:
    return subtotal(prices) * (1 + tax)
```

Discover the functions, their call relationship and their contracts:

```sh
apizr scan .
apizr graph .
apizr inspect example.py
apizr readiness .
```

Generate both interfaces from the same capability:

```sh
apizr generate rest example.py --select total --output-dir .output/rest
apizr generate mcp example.py --select total --output-dir .output/mcp
```

No Docker is needed. The REST bundle includes `app.py`, `openapi.json` and an
artifact manifest; the MCP bundle includes `server.py` and `mcp-tools.json`. Each
bundle includes its runtime requirements. To serve the REST interface:

```sh
python -m pip install -r .output/rest/requirements.txt
uvicorn app:app --app-dir .output/rest --host 127.0.0.1 --port 8000
```

Starting a generated server imports trusted source. See the
[REST guide](https://apizr.outerspace.sh/getting-started/user-guide/rest/) and
[MCP guide](https://apizr.outerspace.sh/getting-started/user-guide/mcp/) for invocation,
stdio/HTTP transport setup and generated bundle integrity checks.

## From source to an interface

```text
Python repository → Scanner → Capability Catalog → Capability Graph
Scripts / notebooks ──────────────→ Capability IR + static readiness
Catalog + Graph ─────────────────→ Repository Readiness (policy evidence)
Capability IR + static readiness → Interface Contract → REST / MCP
                                                          ↓
                                      direct or governed execution
                                             local-process / OCI
```

REST and MCP consume shared contracts. Readiness policies assess static evidence;
execution policies control explicit invocation. Neither discovery nor a `READY`
assessment grants trust or proves runtime safety. Unknown effects remain unknown.
See the [architecture overview](https://apizr.outerspace.sh/architecture/overview/).

## Governed execution

`apizr execute SOURCE CAPABILITY --arguments args.json --policy policy.json`
runs one trusted capability under an explicit policy. Generated REST/MCP servers
can opt in with `--execution-policy policy.json`; their default is direct execution.

The execution backends remain **experimental**: policy contracts and refusal
behavior are tested, but they are not a general untrusted-code service.
A local process provides bounded execution, **not filesystem or network isolation**.
OCI adds Linux container controls and requires a trusted Docker host and worker
image; it is not a VM boundary. Absolute subprocess prohibition remains unsupported.
See the [execution guide](https://apizr.outerspace.sh/getting-started/user-guide/execute/).

## Legacy generation pipeline

The notebook/script → FastAPI → container workflow remains supported:

```sh
apizr --script example.py --output-dir .output/legacy --force
apizr --notebook your-notebook.ipynb --output-dir .output/notebook --force
```

Use a fresh output directory. This independent pipeline is retained for compatibility;
it is not a prerequisite for the compiler commands. See the
[legacy guide](https://apizr.outerspace.sh/getting-started/user-guide/apizr/) and
[compatibility notes](https://apizr.outerspace.sh/getting-started/developer-guide/releases/).

## Limits and trust boundary

Static scanning, inspection and generation do not execute source. Direct servers
import and execute it; governed invocation still requires trusted source and dependencies.
Capabilities currently represent top-level functions, not class methods. Dynamic
bindings, imports and effects can remain unresolved. Generated artifacts are
hashable evidence, not signed attestations. No enterprise control plane is included.
The legacy pipeline's duplicate-definition/overload issue remains tracked in
[#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28).

## Documentation and contributing

- [Start here](https://apizr.outerspace.sh/getting-started/introduction/)
- [Repository scan](https://apizr.outerspace.sh/getting-started/user-guide/scan/),
  [graph](https://apizr.outerspace.sh/getting-started/user-guide/graph/) and
  [readiness](https://apizr.outerspace.sh/getting-started/user-guide/repository-readiness/)
- [0.2.0 release notes](https://apizr.outerspace.sh/releases/0.2.0/)
- [Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/)
- [Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues)

Licensed under [GPL-3.0-or-later](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/LICENSE).
