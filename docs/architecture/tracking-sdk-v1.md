# Tracking SDK v1

This is the target public contract for the 0.4.6 development line; the SDK is
not part of the published 0.4.5 release yet.

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
  publishes the canonical Plan/Run pair.

The public names and responsibilities are fixed here. Argument fields and
evidence identity follow the versioned Plan/Run contracts; implementation
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

The precise duplicate-key, nested-session, size/count and exception-finalization
rules are qualified by the session implementation contract. A workload exception
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

## License

Apizr and `apizr.tracking` are distributed under
[GPL-3.0-or-later](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/LICENSE).
This statement identifies the project's license; it does not determine the legal
obligations of a particular project that imports or combines the SDK. Consult
qualified legal counsel for that assessment.
