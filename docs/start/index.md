---
title: Start here
description: Choose an Apizr workflow and get a first useful result with Python 3.11–3.15.
---

# Start here

Inspect Python code, compare experiments or share selected functions through REST
and MCP. Choose the result you need.

## Choose your first result

| You want to… | Start with |
| --- | --- |
| Understand a script or notebook | [Inspect an experiment](../getting-started/user-guide/experiment-inspection.md) |
| Call a Python function from another application | [REST and MCP quickstart](../getting-started/quickstart.md) |
| Compare training attempts | [Fraud experiment example](../examples/compare-fraud.md) |
| Hand over a generated service | [Operations guide](../operations-guide/index.md) |

## Install for the action you chose

[Install Apizr](../getting-started/install.md) with Python 3.11–3.15 on macOS or Linux.
Then save `example.py`:

```python
learning_rate = 0.05
```

Inspect it:

```sh
apizr experiment inspect example.py
```

The report shows `learning_rate = 0.05` under Parameters, without running the code.

## Continue with your own work

- [User guide](../user-guide/index.md): inspect, track and compare experiments.
- [Developer guide](../developer-guide/index.md): integrate Apizr with your tools.
- [Examples](../examples/index.md): complete files and expected results.
- [Reference](../reference/index.md): exact commands and options.
- [Architecture](../architecture/index.md): components and diagrams.

## What the two MCP workflows do

The **analysis MCP plugin** lets a client inspect your project. A **generated
MCP server** lets a client call the Python functions you selected.
