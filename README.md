# OuterSpace Apizr

**Apizr is an open-source capability compiler for Python codebases.**

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg?cacheSeconds=300)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)

It discovers executable capabilities, builds deterministic contracts and relationships,
exposes eligible capabilities through REST or MCP, and supports governed execution.
Python **3.11–3.14** · GPL-3.0-or-later · Latest stable **0.2.1** · Development line **0.3.0** (`0.3.0.dev0`)

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
the published 0.2.x release; check the installed version with `apizr --version`.

In the **0.3 development checkout**, `python -m pip install .` installs only the
static compiler and Pydantic. Choose optional workflows explicitly:

| Workflow | Checkout installation |
| --- | --- |
| Notebook inspection / generation | `python -m pip install ".[notebook]"` |
| HTTP adapters | `python -m pip install ".[http]"` |
| MCP adapters | `python -m pip install ".[mcp]"` |
| Full historical notebook/script pipeline and web app | `python -m pip install ".[legacy]"` |

Extras combine, for example `".[notebook,mcp]"`. This changes the default
installation from 0.2.1: use `[legacy]` to retain its full dependency stack when
installing a 0.3 wheel. Static scanning, graph, readiness, Python inspection and
bundle generation need no notebook or web framework. Generated servers retain
their own `requirements.txt`; install it before starting a server. Missing
notebook or legacy dependencies produce an installation hint, never an automatic
package installation.

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
                                            ↓ + Exposure Policy (0.3 development)
                                      Exposure Plan
                                            ↓
                              FUTURE repository REST/MCP bundle
Capability IR + static readiness → Interface Contract → REST / MCP
                                                          ↓
                                      direct or governed execution
                                             local-process / OCI
```

REST and MCP consume shared contracts. Readiness policies assess static evidence;
execution policies control explicit invocation. Neither discovery nor a `READY`
assessment grants trust or proves runtime safety. Unknown effects remain unknown.
See the [architecture overview](https://apizr.outerspace.sh/architecture/overview/).

## Repository exposure (0.3 development)

The development checkout adds `apizr expose plan ROOT --policy exposure.json`.
An Exposure Plan records explicitly selected capabilities, intended REST/MCP
interfaces and contract-compatible execution modes over digest-bound repository
evidence. `apizr expose build {rest,mcp} ROOT --policy exposure.json
--readiness-policy readiness.json --output-dir DIR` generates one direct server
for the selected eligible capabilities, with verified multi-source packaging and
module-qualified public names. Both policies must explicitly permit direct execution.
Add `--execution-policy policy.json` for a fresh local worker per invocation, or
an OCI v2 policy with an explicit immutable image and platform for a fresh container.
Every selected capability must permit that backend; existing Readiness eligibility
restrictions still apply. The stable PyPI release remains **0.2.1**. See the [development exposure guide](https://apizr.outerspace.sh/getting-started/user-guide/exposure/).

## Governed execution

`apizr execute SOURCE CAPABILITY --arguments args.json --policy policy.json`
runs one trusted capability under an explicit policy. Generated REST/MCP servers
can opt in with `--execution-policy policy.json`; their default is direct execution.

The execution backends remain **experimental**: policy contracts and refusal
behavior are tested, but they are not a general untrusted-code service.
A local process provides bounded execution, **not filesystem or network isolation**.
OCI adds Linux container controls and requires a trusted Docker host and worker
image; it is not a VM boundary. The optional strict OCI profile can prohibit process and thread creation before
project import; see the [subprocess-deny profile](https://apizr.outerspace.sh/architecture/subprocess-deny/).
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
- [0.2.1 maintenance notes](https://apizr.outerspace.sh/releases/0.2.1/)
- [0.2.0 feature release](https://apizr.outerspace.sh/releases/0.2.0/)
- [Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/)
- [Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues)

Licensed under [GPL-3.0-or-later](https://apizr.outerspace.sh/about/LICENSE/).
