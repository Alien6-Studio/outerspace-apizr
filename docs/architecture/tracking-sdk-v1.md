# Tracking SDK v1

This is the public tracking SDK contract for Apizr 0.4.6.

The tracking SDK records explicit observations from code already running in the
user's process. It does not execute workloads, isolate them, inspect arbitrary
objects or infer scientific correctness.

## Ownership and distribution

The public Python namespace is `apizr.tracking`, owned by the `tracking` domain
in `architecture/packages.toml`. It ships in the `outerspace-apizr` core
distribution; no extra or plugin installation is required. Its runtime
dependencies are the standard library, the existing Pydantic dependency and
the canonical experiment contracts. Scientific libraries remain workload
dependencies and are not imported by the SDK or core.

The existing `apizr.experiments` domain owns Plan/Run values, validation,
canonical serialization, digests and immutable local history. Tracking consumes
those contracts and publishes with `apizr.experiments.store`; it defines no
parallel Plan, Run, history or digest format. Any evidence-schema change is
specified and versioned through the experiment-contract work, not by this SDK.

## Public surface

The v1 surface is deliberately limited to:

- `session(...)`: a context manager that establishes one in-process capture;
- `experiment(...)`: a decorator that captures a function call using that
  session lifecycle;
- `log_parameter(...)`, `log_input(...)`, `log_metric(...)` and
  `log_artifact(...)`: explicit bounded evidence calls;
- `TrackingSession.finalize()`: the terminal operation that validates and
  publishes the canonical Plan/Run pair;
- `TrackingSession.current()`: the current thread/task's capture, or `None`.

The public names and responsibilities are fixed here. Argument fields and
evidence identity follow the [versioned in-process Plan/Run contracts](experiment-evidence-v2.md); implementation
helpers, provider registries and internal context state are private. Active
sessions are context-local, never a process-global mutable "current run".

```python
import apizr.tracking as tracking

with tracking.session(...) as capture:
    tracking.log_parameter(...)
    tracking.log_input(...)
    tracking.log_metric(...)
    tracking.log_artifact(...)
    record = capture.finalize()
```

The context manager establishes and restores the active context; the explicit
logging calls target only that context. The `experiment(...)` decorator uses
the same lifecycle for a function call. Normal context exit finalizes the
capture if it is still open; an explicit `finalize()` returns its canonical
record and is the terminal operation for that capture.

The [qualified SDK reference](../reference/tracking-sdk.md) defines duplicate-key,
nested-session, size/count and exception-finalization rules. A workload exception
must remain visible to its caller; a failed or incomplete capture is never
reported as a successful Run.

## Evidence and trust boundaries

Callers supply metric values, parameters and input identities explicitly. Values
pass through `apizr.experiments.values`; input and artifact fingerprints use the
bounded file primitives owned by `apizr.experiments`. The SDK does not pickle
arbitrary Python objects, traverse unbounded inputs, or write around the
canonical store's validation and publication.

Scientific providers have two distinct roles. Static recognizers consume the
bounded source representation and return candidate evidence without importing
or executing scientific libraries. An in-process adapter that needs a
scientific-library dependency is an out-of-tree extension using the existing
`apizr.extension/v1` mechanism; it reports through the bounded SDK API and
cannot publish directly to the store. There is no second plugin or provider
loader.

`editor_contracts` owns versioned engine capabilities and structured
diagnostics, not a VS Code UI or a transport. Editor operations reuse the same
experiment and provider values; they do not create alternate evidence records.

The execution identities `apizr.execution/v1`, `apizr.runtime/v1` and
`apizr.local-process/v1` remain unchanged. In-process tracking is not a sandbox
and does not change existing execution authorization.

## Live kernel ownership

`tracking/kernel.py` owns bounded observation of an already-running IPython
kernel. It consumes the existing `CellIdentity` contract. It reads the existing
`get_ipython` builtin only at session entry, without importing optional packages,
registering hooks, traversing the user namespace or altering display behavior.
Cell identity, active prompt counter and the raw request's digest remain distinct
from saved-file and function-definition evidence. The cell digest is not used to
claim a defining-code digest or a proven exported notebook binding.

The SDK uses the same session lifecycle, context ownership, failure publication
and canonical store. Suppressed CLI/served captures do not access the kernel.
Cell source observation is bounded to 1 MiB, with the same structured refusal
before business execution for malformed observations. No raw code, connection
information or notebook output is stored.

`scripts/experiment_jupyter_proof.py` owns the Jupyter SDK qualification journey.
The development `jupyter-qualification` group supplies its kernel dependencies;
the installed proof exports their exact hashes, installs the candidate outside
checkout and retains the generated requirements alongside the proof. The CI
package job includes both files in its existing build-evidence manifest.

## Capture cost and observation boundaries

Importing `apizr.tracking` exposes the same public API without loading Pydantic,
experiment models, asyncio or scientific/kernel libraries. Core models are loaded
on explicit session/decorator use; suppressed logging and a served decorator
remain inert. Imports use ordinary canonical modules without an import hook or
a second SDK implementation.

`tracking/budget.py` counts the exact UTF-8 size of admitted immutable observations
without producing complete JSON for each logging call. Fixed schema metadata is
bounded to the five SDK evidence kinds. String escaping is accounted without
creating an escaped copy; the installed Pydantic serializer supplies individual
floating-point numeric tokens so its exponent spelling is counted exactly.
`experiments/values.py` likewise enforces the unchanged 64-KiB value budget during
its bounded freeze traversal, rather than thawing/encoding a second JSON graph.
All type, finite-number, Unicode, nesting and item-count checks remain active.

The 1-MiB aggregate capture limit, including selected call parameters, is checked
before accepting each observation. Call evidence is admitted before business
execution. The initial immutable Plan digest is retained for finalization; the
store still independently validates the published Plan/Run binding and bytes.
Full observation/Run JSON is produced at finalization, not for each logged item.
Plan identity is established before execution; scalar byte accounting is not a
second evidence serialization or a stored JSON cache.

Each selected source/input/artifact observation computes its content digest once
through the existing descriptor-based reader. Distinct log calls reread bytes,
even at the same path, size and timestamps. No path/mtime content cache exists.
Finalization publishes those retained observations without rereading a file or
claiming a new observation time. SDK logging observes the file at the explicit
call; source capture observes entry. Existing CLI before/after workload reads are
unchanged. Environment-specification reads and durable publication remain bounded.

Use the [engine benchmark](engine-performance.md) to measure SDK costs for a
selected source and environment. Import isolation, exact byte boundaries, fresh
file observations and corruption detection also have blocking tests.

## License

Apizr and `apizr.tracking` are distributed under
[GPL-3.0-or-later](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/LICENSE).
This statement identifies the project's license; it does not determine the legal
obligations of a particular project that imports or combines the SDK. Consult
qualified legal counsel for that assessment.
