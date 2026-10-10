---
title: Run experiments and inspect local history
description: Execute a trusted script or supported notebook and distinguish intended Plans from observed Runs.
---

# Run experiments and inspect local history

Available from the **0.4.5 development checkout**; the published version remains
0.4.4. Start with [experiment inspection](experiment-inspection.md).

**`experiment inspect` never executes user code. `experiment run` explicitly
executes trusted user code in a fresh process. The local process is not a filesystem
or network sandbox. User code has the host access allowed by the selected environment
and operating system, including subprocess creation.** There is no interactive
confirmation. Choose `run` only for code you trust.

## A complete first run

Install Apizr in the environment containing your workload's dependencies. Apizr
uses that exact Python interpreter; it does not install dependencies. This example
uses only the standard library and works on Linux and macOS:

<!-- experiment-run:guide -->
```sh
cat > local_run.py <<'PY'
from pathlib import Path
mean = sum([2, 4, 6]) / 3
Path("model.json").write_text('{"mean": 4.0}\n')
PY
apizr experiment inspect local_run.py
RUN=$(apizr experiment run local_run.py --metric mean=mean --output model=model.json --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment show "$RUN"
```

The full lowercase SHA-256 is the Run ID. `show` also accepts a unique prefix of
at least 12 characters; an ambiguous prefix is refused. `show --format json`
returns the complete canonical Plan and Run inside a strict record envelope.
`run --format json` returns a typed result summary; `list --format json` returns
query controls, total verified records, matched count and bounded summaries.
The trust notice goes to stderr, keeping JSON on stdout parseable.

## Execution and environment

The selected root defaults to the source file's parent. `--root PATH` selects an
explicit root containing the source. The worker runs with that root as its working
directory and deliberately adds it to its import path, so same-project imports
work. It does not depend on ambient `PYTHONPATH`. Relative `__file__` names the
inspected source and `__name__` is `__main__`. Fresh process means process-state
isolation, not filesystem isolation.

The default child environment is clean. Repeat `--env NAME` to inherit selected
variables, or choose `--inherit-environment` to inherit all variables. These modes
are mutually exclusive. Plans store selected variable names, never their values.
Apizr discards workload stdout/stderr and sanitizes exceptions; it does not retain
tracebacks, exception messages or arbitrary logs. Deliberately selected metric or
parameter values are evidence: choose them accordingly.

The wall timeout defaults to 60,000 ms; `--timeout-ms` accepts 1–3,600,000 ms and
covers worker startup and execution. Timeout or Ctrl-C terminates the worker's
process group and reaps the direct child. Ordinary descendants in that group are
terminated; independently detached processes are outside this process mechanism.
This is trusted execution, not containment of hostile code. There is no retry.

`run notebook.ipynb` requires the documented `outerspace-apizr[notebook]` extra.
It uses the existing ordinary-Python notebook export, preserving exact notebook
and transformed-byte identities. Stored outputs and execution counts are ignored.
Unsupported magics/shell constructs remain refused. This is not a Jupyter kernel.

## Intended and observed evidence

The runner uses the same Inspection pipeline, then derives a pure Plan. It copies
exact source identities, input selections, static randomness and environment
specification identities. Whole workloads have no selected capability. A parameter
is promoted only when its static candidates agree; conflicting static values are
omitted. Dynamic expressions are never evaluated to derive intent.

The Plan also binds timeout, environment mode/names, root semantics, current
interpreter selection, host filesystem/network/subprocess access, byte limits,
required metric/output selectors and observation policy. It contains no absolute
project root. Changing those controls changes the Plan digest.

The parent rechecks source bytes, transformed notebook identity and every known
selected input identity before launching. The worker rechecks source and known
inputs immediately before executing the supplied exact bytes. A preflight mismatch
is refused as `source_changed` or `input_changed`. No silent reinspection or retry
substitutes a new workload under an old Plan.

| Evidence | Plan intent | Run observation |
| --- | --- | --- |
| Code | Exact inspected raw/executable bytes | Exactly bound source identity |
| Data | Selected static/declared identities | Matching before/after fingerprints, or explicit uncertainty |
| Parameters | Unambiguous static candidates | Valid finite final global bindings with those names |
| Randomness | Static/unknown controls | Runtime application not directly observed |
| Environment | Static lock/config identities | Actual child Python/platform/architecture, selected installed distribution metadata and config identities |
| Metrics | Required selectors | Valid finite captured values |
| Outputs | Required selectors | Successful-workload output reference, size and SHA-256 |

Selected local inputs are fingerprinted again after execution. If their identities
changed between the two observations, the workflow fails with
`input_changed_during_execution` and records neither digest as the one used. Equal
snapshots do not prove every read, or rule out a change followed by restoration.
Remote references are never fetched and retain unknown content. `--input name=ref`
uses the existing input declaration rules. Input and output byte limits default
to 1 GiB each, with `--max-input-bytes` / `--max-output-bytes` capped at 1 TiB.

Final global parameter bindings do not prove which values caused the model or
were consumed on every path. Static seed declarations are never automatically
restamped as runtime facts. Selected distribution metadata comes from the worker's
installed environment; it does not prove which code a shadowing project import
loads. Apizr does not enumerate every installed distribution or run `pip freeze`.

## Metrics and outputs

`--metric roc_auc=score` requires a Python identifier on the right. Apizr reads
that final global binding and validates it through the existing finite JSON
contract: scalars, null, lists and dictionaries are supported within its limits.
No expressions, `eval`, ndarray/DataFrame conversion or object `repr` are used.
A missing, invalid or oversized required metric fails the Run workflow.

Automatic metrics reuse existing static sklearn signals. Only a unique canonical
metric call directly assigned to one top-level name qualifies. Rebinding, ambiguous
branches/functions, multiple calls for the same metric, namespace mutation and
later uses that could mutate the value disable automatic attribution. Use an
explicit selector for those cases. Automatic capture is best effort; required
selectors take precedence. The worker bounds combined captured values to 1 MiB
and prioritizes required metrics over optional bindings.

Automatic output capture reuses unambiguous static joblib declarations. Missing
optional outputs do not fail a successful workload. `--output model=artifacts/model.joblib`
requires that output after success; a missing or unsafe output fails the workflow.
A failed/cancelled workload never captures stale output files as result evidence.
Only identities are stored, never output bytes. Even after success, an existing
file's fingerprint alone does not establish that this invocation created it.

## Failed and cancelled Runs

Normal completion and `SystemExit(0)` succeed. Unhandled exceptions, nonzero exit,
timeout, broken protocol and required observation failures produce failed Runs.
Ctrl-C produces a cancelled Run when parent evidence is available. The store
retains these outcomes; `show` puts status near the top and shows stable diagnostic
codes. Default CLI exit codes are:

| Code | Meaning |
| --- | --- |
| 0 | Successful run, list or show |
| 1 | Persisted failed or cancelled Run; full Run ID is printed |
| 2 | Invalid invocation, preflight refusal or store failure |

A process/OS crash or an unusable store can prevent persistence. Apizr does not
fabricate a record after a failed publication. UTC start/end observations and a
monotonic duration are separate; a reversed wall clock fails with `clock_reversed`
and an unknown end instead of inventing ordered timestamps.

## Local immutable store

`run` defaults to `ROOT/.apizr/experiments/v1`. `list` and `show` default to
`.apizr/experiments/v1` under the current directory. All three accept `--store PATH`;
a relative override is relative to the CLI's current directory.

```text
.apizr/experiments/v1/
├── plans/<PLAN_SHA256>.json
└── runs/<RUN_SHA256>.json
```

The files contain exact `plan_bytes(plan)` and `run_bytes(run)`. New directories
use 0700 and files use 0600. Existing permissions are not silently changed.
Publication stages on the same filesystem, flushes the file, exclusively hard-links
it into place and flushes the directory. The Plan is durable before its Run.
Identical publication is idempotent; existing different bytes are never overwritten.
First writers synchronize directory initialization with an advisory lock on the
store directory itself. An existing partial layout is refused without repair.
A crash may leave an orphan Plan or `.stage-<32 hex>` file. Staging entries are
counted against limits but never followed, treated as evidence or repaired.

Reads reject symlink ancestors, store roots, Plan/Run directories and canonical
files. They validate models, exact canonical bytes, filename hashes and Run-to-Plan
binding. Corruption is refused without automatic deletion, replacement or repair,
even when filters or display limits would otherwise hide it. An absent store is
empty history; a present store with missing canonical components is corrupt.

Traversal is limited to 4,096 entries per Plan/Run directory, 4 MiB per canonical
file and 64 MiB of canonical bytes per query. Concurrent publication may be seen
on a later query; history is not a transaction snapshot. Capacity exhaustion
returns `store_limit`. There is no mutable index or database.

`list` sorts start time descending, then full digest ascending; unknown start times
come last. `--limit` defaults to 20 and has a maximum of 1,000. Exact filters are
`--status success|failed|cancelled`, `--source train.py`, and `--capability ID`.
All canonical records are validated before filtering or applying the display limit.
Whole-workload Runs normally have no capability ID. The default text display is
bounded; JSON contains the complete selected evidence.

New `apizr init` projects ignore `/experiments/` in `.apizr/.gitignore`. For an
already initialized project, add that line yourself if you want Git to ignore local
history. Running experiments does not rewrite an existing ignore file. Evidence
JSON does not become Python source or add capabilities to repository analysis.

This store holds local evidence. See the existing
[external governance boundary](../../reference/external-governance.md) for the
handoff to other systems. Artifact repositories, model registries, remote tracking
and signing stay outside this store. This increment adds no upload, synchronization,
experiment Docker runner, comparison or exposure command.
