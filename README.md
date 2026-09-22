# OuterSpace Apizr

**Apizr is an open-source capability compiler for Python codebases.**

Discover capabilities in existing Python code, assess their static readiness,
explicitly choose what to expose, generate REST or MCP interfaces, and run them
under direct or governed execution policies.

**Latest published stable: 0.3.0 · Released 22 September 2026**

0.3 adds explicit Exposure Plans and multi-module repository REST/MCP bundles,
with direct, fresh local-process or fresh OCI-container execution. Discovery,
generation, direct execution and local execution need **no Docker**.
Python **3.11–3.14** · GPL-3.0-or-later.

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg?cacheSeconds=300)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)

## Install

Use Python 3.11–3.14 in a virtual environment:

```sh
python -m pip install outerspace-apizr==0.3.0
apizr --version
```

The base installation requires only Pydantic for static Python workflows. Optional
workflows require explicit extras (this changes the default installation from 0.2.1):

| Workflow | PyPI installation |
| --- | --- |
| Notebook inspection/generation | `python -m pip install "outerspace-apizr[notebook]==0.3.0"` |
| HTTP adapters | `python -m pip install "outerspace-apizr[http]==0.3.0"` |
| MCP adapters | `python -m pip install "outerspace-apizr[mcp]==0.3.0"` |
| Complete historical pipeline/web app | `python -m pip install "outerspace-apizr[legacy]==0.3.0"` |

Extras combine, for example `"outerspace-apizr[notebook,mcp]==0.3.0"`. Choose `[legacy]`
to retain the full 0.2.1 stack. Generated servers keep their own requirements.

## One repository, two public capabilities

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

Discover, understand, assess, explicitly select, then expose:

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
The MCP bundle exposes the same two names. Install its `requirements.txt`, then run
`python .output/mcp/server.py --transport stdio` or use `--transport streamable-http`.
These generated servers execute trusted code. Use a fresh output directory when
regenerating. Discovery and generation do not execute project source.

## Choose execution boundaries

| Mode | Boundary | State between calls |
| --- | --- | --- |
| Direct | Transport process | Persists |
| Governed local-process | Fresh process per call | Resets |
| Governed OCI | Fresh container per call | Resets |

Add `--execution-policy` for governed execution. Local workers provide time and
input/output bounds, environment control and process-group cleanup; they do not
isolate host filesystem or network access. OCI adds reviewed Linux container
controls using an immutable image ID/platform and the repository worker protocol.
It is not a VM or an untrusted-code guarantee. The optional
[strict OCI subprocess-deny profile](https://apizr.outerspace.sh/architecture/subprocess-deny/)
blocks process and thread creation before project import. Local mode cannot enforce it.

See the [policy examples and exposure guide](https://apizr.outerspace.sh/getting-started/user-guide/exposure/)
for local/OCI commands, policy composition and image prerequisites. Apizr does not
infer/install repository application dependencies or package arbitrary repository
data files. The separate legacy pipeline supports explicit requirements and resources.

## Eligibility, selection and interfaces

**Readiness** is evidence-based eligibility. **Exposure Plan** is the operator's
explicit decision. **Bundle** is the generated public interface. Dependencies
are packaged as support, never automatically exposed. All stages bind deterministic
evidence; neither `READY` nor a generated bundle establishes trust or runtime safety.

[Start here](https://apizr.outerspace.sh/getting-started/introduction/) ·
[Architecture](https://apizr.outerspace.sh/architecture/overview/) ·
[0.3 release notes and migration](https://apizr.outerspace.sh/releases/0.3.0/)

## Existing workflows and limits

0.2 single-source `inspect`, `generate rest/mcp` and `execute` workflows remain
supported, as does the legacy `apizr --script` / `--notebook` pipeline. There is no
automatic migration or publication. Capabilities remain top-level functions;
class/method exposure and an enterprise control plane are outside this release.

The legacy pipeline now supports configured notebook cell selection, resource
packaging, explicit image builds and installed plugins. It inventories classes and
methods separately, and refuses ambiguous selected definitions/overloads. See the
[notebook configuration guide](https://apizr.outerspace.sh/modules/notebook-transformr/).
Static readiness/exposure v1 adapters retain their original control vocabulary;
the strict OCI profile is selected in the execution policy.
See [compatibility notes](https://apizr.outerspace.sh/getting-started/developer-guide/releases/).

[Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/) ·
[Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues) ·
[GPL-3.0-or-later](https://apizr.outerspace.sh/about/LICENSE/)
