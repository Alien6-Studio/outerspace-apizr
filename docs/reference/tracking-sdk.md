# In-process tracking SDK (0.4.6 development)

`apizr.tracking` ships in the core wheel. It requires no optional extra,
scientific library or tracking server. It records explicit observations from
trusted code already executing in your process; it does not launch or isolate
that code. It writes the same private local history used by the CLI runner.

## Explicit sessions

```python
from pathlib import Path
from apizr import tracking

root = Path.cwd()
with tracking.session(root=root) as capture:
    tracking.log_parameter("learning_rate", 0.1)
    tracking.log_input("in_memory")  # Content is explicitly unknown.
    tracking.log_metric("score", 0.75)

record = capture.record
assert record is not None and record.run.status == "success"
print(record.run_digest)
```

The default store is `ROOT/.apizr/experiments/v1`. This directory name is the
existing history location; it can contain independently versioned v1 and v2
artifacts. `store=Path(...)` selects another explicit directory. `source="train.py"`
optionally fingerprints a root-relative Python or notebook file at session start.
Omit it for unknown file evidence: an in-memory function is not proof of saved
source bytes. `distributions=("numpy",)` records selected installed metadata at session start
without importing libraries. Unobserved random seeds remain unknown.

`log_input("training", "data.csv")` fingerprints one selected local regular
file. A `uri=` reference records unknown remote content and performs no download.
`log_artifact("model", "model.joblib")` fingerprints current bytes without
deserializing them. Both use core bounded file admission: absolute paths, parent
traversal, symlinks and nonregular files are refused. `max_file_bytes=` defaults
to 1 GiB and accepts the existing 1 TiB hard maximum.

Each evidence section accepts at most 256 names. Duplicate names are refused;
the first value remains intact. Values use the existing finite, immutable JSON
bounds (64 KiB per value, depth 16, 4096 nodes). Total explicitly logged evidence
is bounded to 1 MiB per session. A caught logging refusal still makes the final
Run failed. Observed parameters are not retroactively presented as Plan intent.

Sessions are context-local. Another thread or async task cannot log into the
parent's session; it may open its own independent session. Nested captures in
the same context are refused and recorded as failure. `TrackingSession.current()`
returns only the session owned by the current thread/task.

Normal exit finalizes once. `capture.finalize()` explicitly ends the capture and
returns its canonical record; repeated finalization returns that record and
further logging is refused. Work performed after explicit finalization is outside
the capture. Business exceptions propagate unchanged. Interrupted/cancelled
captures are `cancelled`; other business failures are `failed`. If publication
also fails, the original business exception remains visible with a bounded note;
`capture.publication_error` records the publication refusal. No exception message,
stdout, stderr or notebook display output is collected.

## Decorated calls

```python
from pathlib import Path
from apizr import tracking


@tracking.experiment(parameters=["learning_rate"], root=Path.cwd())
def fit(learning_rate: float, secret: str = "not-recorded") -> float:
    tracking.log_metric("score", 0.75)
    return 0.75


assert fit(0.1) == 0.75
```

Only selected argument names are recorded, including their defaults. Unknown or
duplicate selections fail when the decorator is applied. Decoration starts no
capture and reads no source file. Each call produces one Run; a decorated call
inside another capture follows the same nesting refusal. Ordinary and async
functions retain their signature, metadata, return object and exceptions.
Generator functions are explicitly unsupported because their iteration has a
separate lifecycle.

Selected DataFrames, models, arrays and other non-JSON objects are recorded as
unknown values with a bounded type name where safely available. They are never
pickled, converted, traversed or represented with `repr()`. Use an explicit
`log_artifact` call for a serialized file you want to identify by content.

## Live Jupyter captures (0.4.6 development)

Run the ordinary session or decorator inside an existing IPython kernel:

```python
from pathlib import Path
from apizr import tracking

with tracking.session(root=Path.cwd()) as capture:
    tracking.log_input("training_frame")
    tracking.log_parameter("threshold", 0.5)
    tracking.log_metric("score", 0.75)

print(capture.record.run.capture.cell.execution_count)
```

The session observes the active execution when entered, even if it was created
in an earlier cell. It records the frontend's optional cell identifier, the
active prompt counter and a bounded SHA-256 digest of the raw execute-request
source. The next-input counter is not mistaken for the current execution.
These are kernel observations; raw cell code and outputs are not retained.

Without an explicit `source`, saved-file evidence is unknown. Supplying a
`source="training.ipynb"` observes that file independently; it does not prove
that an unsaved or re-executed cell matches the saved notebook. No exporter
sidecar or generated Python file is required for live capture.

Each session entry or decorated call publishes its own Run. Re-executing a cell
creates new execution identities; redecorating a redefined function creates a
new definition identity. Decorated calls retain their defining function binding
and observe the calling cell separately. Objects already in memory stay unknown
unless explicitly logged through a supported bounded operation. The example's
`log_input("training_frame")` records an unknown input, not a serialization of
the frame.

An interruption publishes a `cancelled` Run, restores the active context and
leaves `KeyboardInterrupt` visible to Jupyter. Existing stdout, stderr, plots,
display identifiers and display updates remain visible. Importing the SDK or
applying a decorator does not start a kernel or register IPython hooks.

The real-kernel qualification uses **ipykernel 7.4.0**, **IPython 9.17.1** and
**jupyter-client 8.10.0**, on the supported Python 3.11–3.15 Linux/macOS CI
targets. Frontend-specific behavior in JupyterLab, classic Notebook and VS Code
notebooks is not separately qualified by this kernel proof. Kernel packages
belong to the user's notebook environment, not to the SDK's runtime dependencies.
The [Jupyter protocol](https://jupyter-client.readthedocs.io/en/latest/messaging.html)
and [ipykernel parent-request API](https://ipykernel.readthedocs.io/en/stable/api/ipykernel.html#ipykernel.kernelbase.Kernel.get_parent)
define the observed context.

See the runnable [live-capture notebook](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.6/examples/tracking/jupyter-capture.ipynb).

## Shared CLI history and evidence export

```sh
apizr experiment list --store .apizr/experiments/v1
apizr experiment show RUN --store .apizr/experiments/v1 --format json
apizr experiment diff RUN_A RUN_B --store .apizr/experiments/v1 --format json
```

Lists and displays show the capture mode, producer, selected parameters and
metrics. CLI JSON lists use the explicit v2 history view, including when listing
v1 Runs. Original v1 Plan/Run/record bytes and digests stay unchanged; historical
producer details absent from v1 are unknown. `list_runs` retains its v1-only
default view for Python callers, with `include_values=True` for the enriched v2
view. `read_history` accepts both schemas. `history_bytes(show_run(...))` exports
the validated record with canonical Plan/Run values and both digests; no separate
export format or identity is introduced.

Comparison is pure and reports capture modes and recorded evidence differences
without causal conclusions. A v1 CLI Run and v2 SDK Run can be compared directly.
When `experiment run` launches an instrumented script, SDK publication is disabled
inside that worker: the outer runner owns the single authoritative record. SDK
logging does not become an alternate source of automatically inferred metrics.

See the [v2 evidence contract](../architecture/experiment-evidence-v2.md) and
[SDK ownership contract](../architecture/tracking-sdk-v1.md).

## Expose an observed Python source

For a serving function, use literal decorator options so the static compiler can
establish the import binding. Save this as `prediction.py`:

```python
from apizr import tracking


@tracking.experiment(
    parameters=["value"],
    source="prediction.py",
    distributions=("outerspace-apizr",),
)
def predict(value: int) -> int:
    tracking.log_metric("value", value)
    return value * 3


if __name__ == "__main__":
    predict(4)
```

Run `python prediction.py` in that directory, then use `apizr experiment list`
to find its Run. Prepare an explicit
[repository analysis permission](operator-policy.md#authorize-repository-analysis)
in `operator.json`. With the exact SDK wheel retained in `wheelhouse/`, select the
recorded dependency and its evidence explicitly:

```sh
apizr experiment expose RUN --root . --operator-policy operator.json \
  --capability python:prediction:predict --interface rest \
  --dependency outerspace-apizr --dependency-wheelhouse wheelhouse \
  --allow-conditional --exclude-dir .output --output-dir .output/rest
```

Replace `RUN` with its digest. Use `--interface mcp` and another output directory
to select MCP. Dependency versions come from the Run; the wheel's exact bytes
establish its import providers. `--allow-conditional` opts into the existing
repository refinement, whose evidence checks still apply. It does not bypass
unknown decorators, source admission or missing dependencies.

Exposure checks the current Python file and selected artifacts against recorded
digests. It never reruns or retrains the workload. An unknown source is refused;
SDK notebook observations without a proven executable binding are also refused.
The derived exposure v2 retains the original capture and observed source, with
the selected static module kept separately. It never rewrites history or turns
an unknown defining-code digest into known runtime evidence.

In a generated SDK-dependent service, `APIZR_SERVED_PROCESS=1` is set before
project imports. The decorator keeps the original function binding and SDK
logging creates no session or store writes. Governed worker processes use the
same suppression. Bundles whose retained source imports no SDK acquire no SDK
dependency or capture marker.

Dynamic decorator configuration, shadowed imports and stacked decorators remain
conditional. See the [source-only binding rule](../architecture/capability-readiness-v1.md#proven-sdk-decoration-046).
