---
title: What do REST and MCP expose?
description: Use two client interfaces for the same selected Python contract.
---

# What do REST and MCP expose?

REST and MCP are two ways for a client to call selected Python capabilities.
They adapt the same retained function contract to different protocols.

| Interface | Client action | Generated description |
| --- | --- | --- |
| REST | Send an HTTP request to a selected operation. | OpenAPI contract and server adapter. |
| MCP | Discover tools and call a selected tool from an MCP client. | Tool descriptions, input schemas and server adapter. |

The [Quickstart](../getting-started/quickstart.md) makes real calls through both
interfaces. Use the [REST guide](../getting-started/user-guide/rest.md) or
[MCP guide](../getting-started/user-guide/mcp.md) for a single source file or
notebook, and the [repository guide](../getting-started/user-guide/exposure.md)
when local helpers span several files.

## What the adapter establishes

The adapter validates supported input shapes and invokes the selected function
under its configured execution mode. Private helpers remain private. A declared
return annotation is descriptive evidence; it does not establish scientific
correctness or add runtime return enforcement.

An MCP tool does not by itself choose an AI model, grant the model authority or
guarantee a useful answer. A REST endpoint does not provide deployment, identity
management or application authorization. Your application and infrastructure
remain responsible for those decisions.

Read the [REST generator](../architecture/rest-generator-v1.md) and
[MCP generator](../architecture/mcp-generator-v1.md) contracts for their exact
supported shapes and limitations.

[Watch Part III: REST](index.md#03-rest) ·
[Watch Part IV: MCP](index.md#04-mcp)

**Next step:** [Make your first calls](../getting-started/quickstart.md) or
[continue with the experiment path](index.md#experiment-path-recordings-coming-later).
