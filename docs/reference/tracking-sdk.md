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
