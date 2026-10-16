# Work with your Python code

Use this guide when you know your script or notebook and want to understand its
results or make one calculation usable elsewhere. You will inspect evidence,
optionally record trusted runs, then select and call a function.

## Before you begin

Follow [Install Apizr](../getting-started/install.md). Know which interpreter
contains your workload dependencies. Inspection needs no scientific framework;
execution uses the interpreter that runs Apizr and needs those dependencies there.
An isolated `uv tool` or `pipx` installation does not inherit notebook packages.

## 1. Read before you run

Choose [experiment inspection](../getting-started/user-guide/experiment-inspection.md)
for a training workflow, or [source inspection](../getting-started/user-guide/inspect.md)
for a function's interface. For `example.py` containing `learning_rate = 0.05`:

```sh
apizr experiment inspect example.py
```

Read the Data references before proceeding. A dynamic filename or absent runtime
metric is an unknown, not a missing score to invent. A captured parameter is a
source candidate. It becomes observed evidence only when a Run captures it.

## 2. Record and compare when it helps

For code you trust, [record a Run](../getting-started/user-guide/experiment-runs.md)
in the workload environment. The worker has host access; local Run is not a
filesystem or network sandbox. Select useful metric/output names deliberately.
Use `apizr experiment list` and `show` to find a recorded result, then
[compare two Runs](../getting-started/user-guide/experiment-comparison.md).

The [fraud scenario](../examples/compare-fraud.md) changes synthetic data while
keeping the notebook unchanged. Read changed data identity separately from
changed metrics: a difference report does not establish causality.

## 3. Share a function

[Choose which functions are public](select-functions.md). A helper can be included
in the generated files while remaining unavailable to clients. Choose REST for
an HTTP consumer or MCP for a tool consumer. Neither choice requires an AI account.
The [business quote](../examples/business-quote.md) goes straight from existing
functions to both interfaces; the [prediction scenario](../examples/share-prediction.md)
uses a selected successful Run and its model.

## 4. Check a real result

Generation creates files; it does not start a server. Install the generated
requirements, start the service locally, then send the documented request.
Check public routes/tool names as well as the business response. Stop processes
when finished. The [local service procedure](../operations-guide/local-service.md)
provides the lifecycle for your own bundle.

Continue with [notebooks and application files](notebooks.md) when adapting the
example, or [refused functions](troubleshooting.md) when generation stops.
