# OuterSpace Apizr

Connect selected Python functions to AI agents through MCP,
or expose them as REST APIs.

Apizr is an **open-source capability compiler**: analyze existing Python code,
choose which functions are public, generate their interfaces, and define how
they execute. Your business logic stays in Python.

**[Quickstart: make your first MCP and REST calls](https://apizr.outerspace.sh/getting-started/quickstart/)** ·
[The full journey](https://apizr.outerspace.sh/getting-started/introduction/)

Follow [Install Apizr](https://apizr.outerspace.sh/getting-started/install/), then
the Quickstart. See the [release history](https://github.com/Alien6-Studio/outerspace-apizr/releases)
for version-specific functionality, compatibility and verified publication.
The journey is Python code → discover/select capabilities → expose as REST/MCP
→ optionally deliver as OCI.

Apizr **0.4.4** adds portable JSON evidence export/verification and a bounded
HTTPS check for ambiguous first-publication diagnostics. See the
[release record](https://apizr.outerspace.sh/releases/0.4.4/) and
[external governance handoff](https://apizr.outerspace.sh/reference/external-governance/)
for scope, validation and integration limits. Publication status is recorded in
the [release history](https://github.com/Alien6-Studio/outerspace-apizr/releases).

Python **3.11–3.14** · GPL-3.0-or-later.

The `0.4.5` development branch recognizes supported Python `TypedDict` model
payloads as shared, nested JSON inputs for REST and MCP. See the
[source inspection guide](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/docs/getting-started/user-guide/inspect.md#structured-model-inputs-with-typeddict)
for an executable example and the current declaration limits.

It also adds concise MCP analysis: ask for `view="summary"`, then inspect one
function with `view="detail", capability_id="python:model:predict"`. The
[analysis server guide](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/docs/reference/apizr-mcp-server.md#start-with-a-small-view-045-development)
explains dependency evidence, pagination and localized exposure refusals.

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg?cacheSeconds=300)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)
[![OuterSpace Apizr MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr/badges/score.svg)](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr)
[![MCPLookup Trust Index: silver, 80 out of 100](https://mcplookup.com/badge/io.github.Alien6-Studio/outerspace-apizr?embed=a6d68610-7a46-4689-8add-e364a971ddbf)](https://mcplookup.com/badge/go/a6d68610-7a46-4689-8add-e364a971ddbf/io.github.Alien6-Studio/outerspace-apizr)

## Install with uv

With [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.11–3.14 installed:

```sh
uv tool install outerspace-apizr==0.4.4
```

![Install Apizr 0.4.4 with uv](https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/54e6c13fe8f2bed62f4ac52a0024002df113df19/docs/assets/videos/uv-install.gif)

## Choose your path

Have a training script or notebook? The **0.4.5 development checkout** adds a
zero-execution first step:

<!-- experiment-inspection:readme -->
```sh
apizr experiment inspect train.py
```

See code, data, parameters, randomness, environment, metrics, outputs and serving
candidates. Follow the [experiment inspection example](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/docs/getting-started/user-guide/experiment-inspection.md)
for setup, notebooks and JSON. No science-framework installation is needed.

| Your goal | Start here |
| --- | --- |
| Understand a training script or notebook (0.4.5 development) | [Inspect an experiment without running it](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/docs/getting-started/user-guide/experiment-inspection.md) |
| Expose Python functions as MCP tools or REST endpoints | [Install](https://apizr.outerspace.sh/getting-started/install/) → [Quickstart](https://apizr.outerspace.sh/getting-started/quickstart/) |
| Analyze a project from an MCP client | [Install the MCP profile](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile) → [analysis server](https://apizr.outerspace.sh/reference/apizr-mcp-server/) |
| Build and deliver a service | [Install OCI or delivery](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile) → [OCI](https://apizr.outerspace.sh/reference/oci-service-plugin/) and [Attest](https://apizr.outerspace.sh/reference/attest-delivery-plugin/) |
| Initialize and diagnose a project (0.4.2) | [Safe init, read-only doctor and shell completion](https://apizr.outerspace.sh/getting-started/onboarding/) |
| Validate/build in CI (0.4.2) | [GitHub Action, GitLab component source and apizr ci](https://apizr.outerspace.sh/getting-started/user-guide/ci-integrations/) |

The core handles supported static analysis and generation. Generated servers have
their own runtime dependencies. Optional plugins live in separate environments;
installation, activation and operator authorization are independent decisions.

Upcoming 0.4.5 lets you expose an independent function while unrelated experiments
remain unfinished; see the [research repository example](https://apizr.outerspace.sh/getting-started/user-guide/exposure/#work-with-unfinished-research-code).


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
[Apizr analysis MCP server](https://apizr.outerspace.sh/reference/apizr-mcp-server/)
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
Apizr 0.4.2 also exports verified REST bundles to
[Postman, Bruno and Insomnia collections](https://apizr.outerspace.sh/getting-started/user-guide/client-collections/),
with deterministic files and safe local regeneration.

The [historical pipeline](https://apizr.outerspace.sh/getting-started/user-guide/apizr/)
is a separate compatibility path. See
[the full journey](https://apizr.outerspace.sh/getting-started/introduction/#compatibility-and-limits)
for dependency, resource and exposure limits.

[Watch the demo](https://apizr.outerspace.sh/#watch-apizr-in-action) ·
[Architecture](https://apizr.outerspace.sh/architecture/overview/) ·
[Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/) ·
[Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues) ·
[GPL-3.0-or-later](https://apizr.outerspace.sh/about/LICENSE/)
