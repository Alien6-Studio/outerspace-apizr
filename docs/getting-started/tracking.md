---
title: Record your first SDK experiment
description: Capture a Python block, compare decorated calls, then use the same history from Jupyter and VS Code.
---

# Record your first SDK experiment

Apizr **0.4.6** records experiments in your existing Python environment;
no tracking server or scientific extra is needed.
Use a fresh working directory outside the Apizr checkout:

```sh
python -m pip install outerspace-apizr==0.4.6
apizr --version
```

Use the Python environment in which your workload already runs. The SDK observes
trusted code inside that process and does not isolate its filesystem or network
access. For the existing workflow without instrumentation, follow
[the notebook-to-service guide](data-science.md).

## 1. Record a block

Run this in your working directory. It writes one Run and prints its identifier:

<!-- tracking-journey:session -->
```sh
python - <<'PY'
from pathlib import Path
from apizr import tracking

measurements = [0.7, 0.8, 0.9]
with tracking.session(root=Path.cwd()) as capture:
    tracking.log_input("measurements")
    tracking.log_parameter("threshold", 0.5)
    tracking.log_metric("mean", sum(measurements) / len(measurements))
print(capture.record.run_digest)
PY
```

`measurements` is in memory, so its content identity is unknown. For a local file,
use `tracking.log_input("training", "data.csv")`; for an output you already wrote,
use `tracking.log_artifact("model", "model.joblib")`. Apizr fingerprints selected
bytes without loading a model. It does not automatically record every variable.

## 2. Compare two calls

Choose which arguments to record. Each ordinary call creates one Run:

<!-- tracking-journey:decorator -->
```sh
python - <<'PY'
from pathlib import Path
from apizr import tracking

measurements = [0.7, 0.8, 0.9]

@tracking.experiment(parameters=["threshold"], root=Path.cwd())
def evaluate(threshold):
    score = sum(value >= threshold for value in measurements) / len(measurements)
    tracking.log_metric("score", score)
    return score

print(evaluate(0.75))
print(evaluate(0.85))
PY
```

The scores are `0.6666666666666666` and `0.3333333333333333`. Find their Run
identifiers, then show or compare them:

<!-- tracking-journey:history -->
```sh
apizr experiment list
```

```sh
apizr experiment show RUN_A
apizr experiment diff RUN_A RUN_B
```

Replace the placeholders with identifiers from the list. The shared local store
is `.apizr/experiments/v1`; its directory name also accommodates v2 SDK records.
Diff describes recorded changes and makes no causal claim. Exceptions still
propagate to your program: a failed or interrupted capture records its status
without saving exception messages, stdout or display output.

## 3. Use the same calls in Jupyter

Install Apizr 0.4.6 in your existing kernel environment and open the
[runnable live-capture notebook](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.6/examples/tracking/jupyter-capture.ipynb).
It contains the block and the two decorated variants above. Run its cells in order,
then use `apizr experiment list` from the notebook's working directory and the
same environment. Re-executing a cell produces a new Run, retaining its execution
count and cell identity when the frontend supplies one.

For supported kernel versions and frontend limits, see the [Jupyter reference](../reference/tracking-sdk.md#live-jupyter-captures-046-development).
In-memory notebook observations do not establish a saved source or serving
binding. For an eligible saved prediction function, follow
[exposure from SDK evidence](../reference/tracking-sdk.md#expose-an-observed-python-source).
Exposure validates recorded evidence and never reruns training.

## Recognition and privacy settings

The SDK records the values you choose to log. To change how Apizr recognizes
scientific libraries during source inspection, see
[scientific providers](../reference/scientific-providers.md).
Read [telemetry and privacy](../about/telemetry.md) before enabling optional telemetry.


## 5. Open the history in VS Code

Install the qualified VSIX, trust your workspace and explicitly select the
Apizr 0.4.6 engine and the repository/history permissions described in the
[VS Code guide](../reference/vscode.md). **Apizr: Refresh Experiment Runs** reads
the same store; select a Run to show it and two to compare them. Restricted Mode
starts no engine. Inspection reads saved source; unsaved changes mark the result
stale. No training is started by inspecting or browsing history.

See [migration from 0.4.5](../releases/migrate-0.4.6.md) for store, CLI and
compatibility details, and [Academy experiment lessons](../academy/index.md#experiment-path-recordings-coming-later)
for the recordings and their written guides.

<span id="4-choose-static-recognition-and-privacy-settings"></span>
