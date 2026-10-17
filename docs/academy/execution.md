---
title: Where does execution happen?
description: Distinguish static generation, direct calls, fresh processes and container execution.
---

# Where does execution happen?

Inspection and generation read retained source evidence. Running a generated
service and calling its functions execute your Python code. Choose an execution
boundary appropriate for code and dependencies you trust.

| Mode | Where a call runs | What persists between calls |
| --- | --- | --- |
| Direct | Inside the service process | Process state can persist. |
| Local-process | In a fresh worker process | Worker state resets. |
| OCI | In a fresh governed worker container | Worker state resets. |

Governed execution can enforce configured time, input and output bounds. Local
process execution does not isolate the filesystem or network. OCI applies its
configured container controls; it is not a guarantee for running untrusted code.
Unavailable governed backends refuse a call instead of silently switching modes.

## A service image and a worker boundary are separate choices

Part V packages a REST or MCP service in an OCI image. Packaging a server in a
container does not itself select a fresh governed OCI worker for each call.
Review the service's execution policy separately.

Start with the [execution guide](../getting-started/user-guide/execute.md) and
the [OCI service guide](../reference/oci-service-plugin.md). For the complete
boundaries, see [repository execution](../architecture/governed-repository-runtime.md)
and [OCI container execution](../architecture/oci-container-runtime-v1.md).

In-process SDK tracking observes code already running in your Python process.
It adds no isolation or execution authorization; its
[reference](../reference/tracking-sdk.md) describes the capture limits.

[Watch Part V: OCI](index.md#05-oci)

**Next chapter:** [What do REST and MCP expose?](interfaces.md)
