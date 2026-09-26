# OuterSpace Apizr

Connect selected Python functions to AI agents through MCP,
or expose them as REST APIs.

Apizr is an **open-source capability compiler**: analyze existing Python code,
choose which functions are public, generate their interfaces, and define how
they execute. Your business logic stays in Python.

**[Quickstart: make your first MCP and REST calls](https://apizr.outerspace.sh/getting-started/quickstart/)** ·
[The full journey](https://apizr.outerspace.sh/getting-started/introduction/)

**Latest published stable: 0.3.0 · Released 22 September 2026**

**Preparing 0.4 — not released.** This repository and the site also describe
unreleased work. Follow the [0.4 development guide](https://apizr.outerspace.sh/development/0.4/)
for the Python compiler API, project files, remote Git, isolated plugins,
the Apizr analysis MCP server and OCI/Attest delivery. Those additions are
not part of the stable installation below.

Python **3.11–3.14** · GPL-3.0-or-later.

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg?cacheSeconds=300)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)

## Install

In a Python 3.11–3.14 virtual environment:

```sh
python -m pip install outerspace-apizr==0.3.0
apizr --version
```

The [Quickstart](https://apizr.outerspace.sh/getting-started/quickstart/)
shows how to create that environment, fetch a versioned example, select exactly
two public functions, generate a server and call it. Static Python analysis needs
only the base installation. Generated MCP and REST servers have their own
`requirements.txt`, installed explicitly before running them.

For optional notebook, HTTP or historical pipeline workflows, see the
[installation choices](https://apizr.outerspace.sh/getting-started/introduction/#install).

## Expose the functions you choose

<span id="one-repository-two-public-capabilities"></span>
<span id="eligibility-selection-and-interfaces"></span>

**Readiness** reports whether the available code evidence supports an interface.
An **exposure policy** names the functions you choose to make public. A **bundle**
is the generated server, its contracts and the source needed by those functions.
Being ready never makes a function public automatically.

| Connect through | Start with |
| --- | --- |
| MCP tools for agents and other clients | [Generate MCP and make two calls](https://apizr.outerspace.sh/getting-started/quickstart/#generate-the-mcp-bundle) |
| REST endpoints for applications | [Generate REST and send two requests](https://apizr.outerspace.sh/getting-started/quickstart/#use-rest-instead) |

The generated MCP server calls your selected functions. The separate,
[development Apizr MCP server](https://apizr.outerspace.sh/reference/apizr-mcp-server/)
analyzes repositories and plans exposure; it does not execute their functions.

## Choose execution boundaries

Analysis and generation do not execute the project. Starting a generated server
and calling its functions does: use trusted source and dependencies.
**Direct** mode runs functions inside the server. **Governed** mode uses an
**execution policy** to choose a worker and its required limits: a fresh local
process or an OCI container per call. Local workers do not isolate the host
filesystem or network; containers are not an untrusted-code guarantee.

The direct Quickstart needs no Docker. Read the
[exposure guide](https://apizr.outerspace.sh/getting-started/user-guide/exposure/)
for governed examples and the
[execution boundaries](https://apizr.outerspace.sh/architecture/governed-repository-runtime/)
for their guarantees and limits.

## Existing workflows and limits

Single-source `inspect`, `generate rest/mcp` and `execute` remain supported.
The [historical pipeline](https://apizr.outerspace.sh/getting-started/user-guide/apizr/)
is a separate compatibility path. See
[the full journey](https://apizr.outerspace.sh/getting-started/introduction/#compatibility-and-limits)
for dependency, resource and exposure limits, and
[0.3 release notes](https://apizr.outerspace.sh/releases/0.3.0/) for migration.

[Watch the demo](https://apizr.outerspace.sh/#watch-apizr-in-action) ·
[Architecture](https://apizr.outerspace.sh/architecture/overview/) ·
[Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/) ·
[Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues) ·
[GPL-3.0-or-later](https://apizr.outerspace.sh/about/LICENSE/)
