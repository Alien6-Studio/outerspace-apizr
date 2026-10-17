---
title: Start here
description: Choose an Apizr workflow and get a first useful result with Python 3.11–3.15.
---

# Start here

Apizr helps you understand existing Python work, keep evidence from trusted
executions, and share selected functions with applications or tool clients.
Start with the result you need. Exposing an existing function requires no
Experiment Run.

## Choose your first result

| Your starting point | First action | Observable result |
| --- | --- | --- |
| A script or notebook you want to understand | [Inspect an experiment](../getting-started/user-guide/experiment-inspection.md) | Data references, parameters and unknowns, without running it |
| A function another application needs | [Make your first calls](../getting-started/quickstart.md) | A real HTTP response or MCP tool result |
| Two training attempts | [Compare fraud experiments](../examples/compare-fraud.md) | Recorded differences in inputs and results |
| A service ready for a colleague | [Hand over a service](../operations-guide/index.md) | Checked runtime, bundle and delivery evidence |

## Install for the action you chose

Use Python 3.11–3.15 on a qualified macOS or Linux environment.
[Install Apizr](../getting-started/install.md) is the canonical installation
procedure. The core is sufficient for static Python inspection and generation.
The notebook extra enables conversion; scientific libraries belong to the
workload environment. Generated services install their own requirements.

For a zero-execution first result, save `example.py`:

```python
learning_rate = 0.05
```

Then, in the environment where you installed Apizr:

```sh
apizr --version
apizr experiment inspect example.py
```

Check that Parameters contains `learning_rate = 0.05`. The eight report sections
separate available evidence from unknown facts. No model has run and no metric
value has been measured. You can inspect a pandas script without installing
pandas; you need pandas when you choose to execute that script.

## Continue with your own work

[User guide](../user-guide/index.md) follows a script or notebook from inspection
to optional execution, comparison and sharing. [Developer guide](../developer-guide/index.md)
shows how to integrate the public compiler in your tools. [Operations guide](../operations-guide/index.md)
follows generated services through environments, verification and delivery.
Use [Examples](../examples/index.md) for complete files and expected results,
and [Reference](../reference/index.md) for exact options and contracts.
The [Architecture guide](../architecture/index.md) explains how the components
fit together, with diagrams of compilation, evidence, execution and delivery.

## What the two MCP workflows do

The optional **analysis MCP plugin** lets a client inspect a repository with
Apizr. A **generated MCP server** executes the Python functions you selected.
You can call generated tools with the Python SDK without an AI account.
The [canonical concepts](../reference/concepts.md) explain the shared terms.

[Releases](../releases/0.4.6.md), [Contributing](../about/CONTRIBUTING.md),
[License](../about/LICENSE.md) and [legacy compatibility](../architecture/legacy-behavior-contract.md)
remain available under Reference. The logo always returns to the home page.
