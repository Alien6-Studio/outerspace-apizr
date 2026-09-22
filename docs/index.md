---
template: home.html
title: Apizr — capability compiler for Python
description: Discover capabilities, assess readiness, explicitly select public interfaces and execute Python repositories through REST or MCP.
---

# Apizr

**An open-source capability compiler for Python codebases.**

Discover capabilities in existing Python code, assess their static readiness,
explicitly choose what to expose, generate REST or MCP interfaces, and run them
under direct or governed execution policies.

**Latest published stable: 0.3.0 · Released 22 September 2026**

Python 3.11–3.14 · GPL-3.0-or-later. Install with `python -m pip install outerspace-apizr==0.3.0`.
It adds explicit Exposure Plans and multi-module repository bundles. Discovery,
generation, direct servers and governed local workers need no Docker.

[Try the repository walkthrough](getting-started/introduction.md){ .md-button .md-button--primary }
[Read the 0.3 release notes](releases/0.3.0.md){ .md-button }

## Discover → Understand → Assess

`apizr scan .` inventories Python source without executing it. `apizr graph .`
explains static relationships. `apizr readiness .` evaluates evidence under policy.
Unknown evidence remains unknown; **READY does not mean exposed**.

## Select → Expose

`apizr expose plan` records your explicit capability selection. `apizr expose build`
creates one repository REST or MCP server. If selected A calls helper B, B is
packaged as support and stays private. [Plan exposure](getting-started/user-guide/exposure.md).

## Execute with an explicit boundary

| Mode | Boundary | State |
| --- | --- | --- |
| Direct | Transport process | Persists |
| Governed local | Fresh process per call | Resets |
| Governed OCI | Fresh container per call | Resets |

Local execution provides bounds and cleanup without filesystem/network isolation.
OCI adds reviewed container controls with an explicit immutable worker image; it
is not a VM or an untrusted-code guarantee. The optional
[strict OCI profile](architecture/subprocess-deny.md) prohibits process/thread creation. Source and
application dependencies must be trusted.
[Understand execution boundaries](architecture/governed-repository-runtime.md).

Single-source scripts/notebooks and the [legacy pipeline](getting-started/user-guide/apizr.md)
remain supported. [Previous 0.2.1 notes](releases/0.2.1.md) ·
[Compatibility and migration](getting-started/developer-guide/releases.md).
