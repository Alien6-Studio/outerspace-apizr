# SDK capture costs — 0.4.6 development

Evidence for #322, using the #319 engine benchmark. Before source:
`4e4ab95a2337fb22b52040fb951c7b1c530b29a8`. After source: this implementation,
identified by `sdk_source_sha256` in `after.json`. All SDK source hashes in that
report match the final measured implementation. No published version changed.

Python `3.12.13 (main, Jul 23 2026, 14:33:47) [Clang 22.1.3 ]`; `macOS-27.0.1-arm64-arm-64bit`; local shared arm64
machine, 16 logical CPUs. Same locked environment, five samples per
case, medians below. Raw samples for all original workloads remain in
`before.json` and `after.json`, not just the improving operations. The script's
later source-metadata, cold-capture and profile-EOF additions do not change the
original timed operations. Source/fixture and lock hashes are recorded.

## Measurements

| Operation | Before median (ms) | After median (ms) | Observed change |
| --- | ---: | ---: | ---: |
| `import_tracking` | 235.49783 | 18.35525 | -92.2% |
| `sdk_0_entry` | 0.76867 | 0.88513 | +15.2% |
| `sdk_0_exit` | 1.30725 | 1.31292 | +0.4% |
| `sdk_256_entry` | 0.76596 | 0.79583 | +3.9% |
| `sdk_256_per_value` | 0.00593 | 0.00489 | -17.6% |
| `sdk_256_exit` | 9.64996 | 8.02417 | -16.8% |

Entry includes session construction and entry with already loaded engine
models. Per-value cost covers 256 explicit integer metrics. Exit includes Run
validation and durable publication. No timing here establishes a cross-platform
latency guarantee or a reduction in CI runner-minutes.

Import is lazy: dependency loading moves to explicit capture use. It is not
eliminated. A separate isolated-process comparison, alternating old/new checkout
sources with the **same interpreter and dependencies**, measures import plus the
first empty capture and durable publication: **102.511 ms before →
102.504 ms after**. Five samples per source are retained in
`cold-session.json`. Bytecode caches were precompiled for both checkouts with the same interpreter; OS caches were not evicted. Both SDK and value-admission source paths were asserted in
the child. This comparison was measured in a separate time window on a shared
machine; do not add times from the two experiments. The baseline import sample
can exceed the separate cold-total sample because host load/cache state varied.
The current benchmark records this cold-first-capture case directly as well.

## Profiled work

| Function | Before calls | After calls |
| --- | ---: | ---: |
| `values.py:_freeze` | 3584 | 3584 |
| `__init__.py:dumps` | 3584 | 0 |
| `main.py:model_dump_json` | 256 | 0 |
| `serialization.py:plan_digest` | 5 | 4 |

The finite-value admission call count is unchanged. Its bounded traversal now
counts canonical bytes without thawing and JSON-encoding a second graph. Logging
counts complete observation bytes without `model_dump_json`; floating-point
byte accounting still formats individual numeric tokens with Pydantic to retain
its exact exponent spelling. The profile uses integer metrics, so those tokens
are not needed in this particular case. The initial immutable Plan digest is
retained for finalization. Publication still performs its existing independent
validation, digest and durable-write checks.

Only fixed metadata for five canonical capture types is shared. No user values,
paths, file contents, observation results or mutable active session are cached
between captures. Each explicit file observation retains its own digest; later
calls reread content even when inode, size and mtime are identical. Finalization
uses the retained observations without claiming a new read or observation time.
Existing CLI before/after reads are unchanged.

## Qualification and reproduction

The complete local suite passes **7,669 tests, 74 skipped** in 356.87 seconds.
All **23 existing coverage gates** pass; both `experiments/values.py` and the new
`tracking/budget.py` have **100% line and branch coverage**. Additional benchmark
and capture checks cover the completed cold-case helper, exact byte boundaries,
Unicode/control escaping, finite floats, no JSON copies during logging, fresh
file reads and inert imports/served calls. Six targeted security mutations are
killed. No dependency or security floor was relaxed.

Run `scripts.qualification.experiments.benchmark_engine` as documented in
[the engine baseline](https://apizr.outerspace.sh/architecture/engine-performance/). Use
`--repeats 5 --history-sizes 10` for this SDK-focused measurement; the full history
sizes remain available. To repeat the separate cold comparison, create a clean
read-only worktree at the before commit and call the benchmark's
`cold_session(source, new_store_root)` for each source, using five alternating
isolated processes. The helper verifies its selected checkout and uses the same
locked interpreter. Remove the temporary worktree afterwards.

Readable warm collection profiles accompany the reports. To reproduce them,
resolve imports, then profile one ordinary session with 256 calls to
`log_metric(f"metric_{i}", i)` using `cProfile`, followed by normal context exit.
Binary profiles stay in local evidence, not Git.

This batch also corrects the trailing blank lines in #319/#320 readable profiles
and normalizes the benchmark writer. Their measurements are unchanged; the
complete pre-commit checks now cover the retained evidence before the push.
