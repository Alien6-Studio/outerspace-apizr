---
template: home.html
title: Apizr — capability compiler for Python
description: Discover Python capabilities, inspect their contracts and relationships, and generate REST or MCP interfaces with explicit execution policies.
---

# Apizr

**An open-source capability compiler for Python codebases.**

Understand what existing Python code can expose before connecting it to an API or
a tool client. Scan a codebase, inspect its capability graph, expose eligible
functions through REST or MCP, and execute trusted code under explicit policies.

**Python 3.11–3.14 · Stable 0.2.1 · GPL-3.0-or-later**

Development line: **0.3.0** (`0.3.0.dev0`).
[Exposure planning](getting-started/user-guide/exposure.md) is available in the
development checkout; it is not part of the stable PyPI release.

[Start with a small Python project](getting-started/introduction.md){ .md-button .md-button--primary }
[Read the 0.2.1 release notes](releases/0.2.1.md){ .md-button }

## Discover

`apizr scan .` inventories Python files without importing or executing them.
[Scan your repository](getting-started/user-guide/scan.md).

## Understand

`apizr graph .` reports statically known relationships. `apizr inspect example.py`
explains individual contracts; `apizr readiness .` assesses repository exposure
evidence under a policy. Unknown evidence remains unknown.
[Understand the architecture](architecture/overview.md).

## Expose

Generate REST and MCP interfaces from the same eligible contracts. Start with a
small typed function; no Docker is required for discovery or generation.
[Generate REST](getting-started/user-guide/rest.md) or
[generate MCP](getting-started/user-guide/mcp.md).

## Govern

Choose direct execution or an explicit local-process/OCI policy. Static `READY`
is not a safety guarantee. Local processes do not isolate filesystem/network
access; OCI containers are not VMs. Execution remains experimental and requires
trusted source and infrastructure.
[Understand execution boundaries](getting-started/user-guide/execute.md).

## Existing notebook workflows

Scripts and notebooks remain supported for inspection and generation. The
[Legacy generation pipeline](getting-started/user-guide/apizr.md) is
retained. See [compatibility notes](getting-started/developer-guide/releases.md)
for supported environments and output behavior.
