---
title: What does Exposure select?
description: Choose public functions, interfaces and allowed execution modes while keeping helpers private.
---

# What does Exposure select?

Exposure records your explicit choice of public capabilities, interfaces and
allowed execution modes. A report listing ten ready functions does not make
all ten available to clients.

For the shop example, choose the price and stock functions for REST and MCP.
The generated bundle includes their required local helpers, but those helpers
do not become public operations. Selection determines the client surface.

## Review the selection before building

Follow [selection and private helpers](../getting-started/user-guide/exposure.md)
to create a plan and build the selected interface. Repository analysis requires
an explicit [operator policy](../reference/operator-policy.md); a project file
or an exposure selection does not grant permission to read arbitrary sources.

The plan binds its decisions to retained evidence. Generation produces files
you can review; it does not start a server, deploy an application or execute
your business function.

## Experiments and serving

An experiment Run records observations. Serving an eligible prediction is a
separate decision: select the successful Run and prediction capability, verify
the required evidence and artifacts, then generate the interface. Do not treat
every training step as a public endpoint. Follow the
[experiment exposure guide](../getting-started/user-guide/experiment-exposure.md)
for the supported workflow and refusals.

The [Exposure Plan](../architecture/exposure-plan-v1.md) and
[repository bundle](../architecture/repository-bundle-v1.md) guides describe
the retained contracts and integrity checks.

[Watch Part III: REST](index.md#03-rest) ·
[Watch Part IV: MCP](index.md#04-mcp)

**Next chapter:** [Where does execution happen?](execution.md)
