---
title: Engine performance and budgets
description: Reproducible 0.4.6 development baselines, history admission costs and regression policy.
---

# Measure engine costs

The **Apizr 0.4.6** benchmark records elapsed time and actual function-call
profiles. Timings describe a recorded environment and fixture, rather than a
cross-platform latency promise. No dependency or security gate is disabled.

Run from a disposable checkout with the locked development environment, including
the notebook extra:

```sh
uv sync --locked
uv run --locked python -m scripts.qualification.experiments.benchmark_engine \
  --output /absolute/new/engine-performance --repeats 3
```

The output directory must not exist. All synthetic stores, digest files and
session publications stay under that directory; inspected source is never
executed. `summary.json` records the source revision, dirty state, source hashes,
Python, platform, runner, lock hash, fixture hashes and each sample. The history
profiles are retained as binary `.prof` and readable `.txt` files. The manual
**Engine performance baseline** workflow runs this same command on Linux and
macOS with pinned uv/Python and archives reports for 90 days. It does not add
another matrix to ordinary development pushes.

## Workloads and interpretation

| Measurement | Method |
| --- | --- |
| Imports and CLI startup | Fresh isolated interpreter for `import apizr`, `import apizr.tracking` and `apizr --version`; process startup included |
| Inspection | Real CLI JSON inspection of `examples/data-science/fraud-detection/fraud_detection.ipynb` and a deterministic 500-function Python script; no scientific workload execution |
| SDK | Session entry, each of 256 explicit metric observations, and exit/durable publication; empty sessions measured separately |
| Cold first capture | Fresh process importing the selected checkout's SDK and completing one empty session; includes dependency loading and durable publication |
| Content digests | Existing `_files.py` descriptor-based SHA-256 reader at 0, 1 MiB and 16 MiB; content read on each observation |
| Publication | Existing durable Plan-before-Run publication into a new empty store; fixture construction excluded |
| History | List JSON, show JSON and diff JSON at 10 and 1,000 Runs sharing a canonical v1 Plan; complete validation included |
| Resource refusal | List/show/diff on 10,000 canonical fixture Runs, without changing production limits |
| Editor | Real stdio process round trips for discovery, list, show and diff on the 10-Run store, with explicit operator grants |

The 10,000-Run scenario must return `store_limit`: the current admission ceiling
is 4,096 entries per directory and 64 MiB of aggregate reads. Its elapsed time
measures refusal, not successful history throughput. `--history-sizes 4096` adds
an optional measurement at the supported entry ceiling. Increasing capacity is a
separate contract decision.

Fixture construction uses direct canonical file writes to avoid timing quadratic
store preparation. Measured publication uses the real durable public API. The
benchmark does not clear OS caches; histories and files may be warm. There is no
application cache across commands. Compare the same fixtures, Python and machine
under similar load, using retained samples rather than one timing.
The machine is shared; unrelated workloads are not stopped or controlled by the
benchmark. Reported changes are observations, not isolated causal estimates.
Per-phase SDK measurements use already loaded engine dependencies. The cold first
capture is separate: making the SDK import lazy moves initialization to explicit
use and does not establish an equal saving in end-to-end capture latency.

## Admission work and budgets

All list/show/diff commands still validate the **complete bounded store**, including
orphan Plans, filtered-out Runs and records beyond the display limit. A hash match
does not replace schema, canonical-byte or binding validation. Diff resolves both
identities in one traversal; it never presents a targeted check as global proof.

The operation-local Plan cache reuses a fully validated immutable value after its
canonical bytes and SHA-256 filename have been checked. Each Run receives the
same schema/canonical-byte checks and Run-to-Plan identity check before record
assembly. Nothing is cached between calls. Public APIs accepting record objects
still revalidate them, including forged `model_copy` values. Durable publication
and all existing bounds remain unchanged.

Two kinds of budgets have different enforcement:

| Budget | Initial tolerance | Enforcement |
| --- | --- | --- |
| Wall time, every measured operation | Median at most `2 × initial baseline + 50 ms` on the same environment/fixture; investigate larger movement | Informational until repeated hosted samples establish variance; no flaky shared-runner threshold |
| History artifact admission | One JSON decode per stored artifact per complete traversal; one shared Plan decode for these fixtures | Blocking regression tests using the real reader |
| Stored comparison | One complete traversal for both identities, including identical/prefix identities | Blocking CLI regression test |
| Safety and canonical output | Zero tolerance for changed corruption refusals, fabricated identities or changed reviewed diff bytes | Existing negative/golden tests, additional admission tests and security mutations |
| Resource limits | Existing byte, entry and display bounds; 10,000 Runs explicitly refused | Blocking resource-refusal tests; no benchmark patches to production bounds |

The timing tolerance derives from the first measurements, allows substantial
startup/IO noise, and is a review trigger rather than an automatic performance
claim. Follow-up optimization issues reuse these baselines: shared analysis
(#321) and SDK capture costs (#322). The SDK figures here include existing value
admission and serialization; this history change does not optimize SDK capture.

The earlier [pytest comparison](https://github.com/Alien6-Studio/outerspace-apizr/issues/296)
remains the test-suite baseline: Linux 547.35 → 294.52 seconds, macOS
893.80 → 434.01 seconds for the qualified serial/parallel comparisons. The engine
benchmark does not rerun those full-suite performance experiments.

## First measurements

Run the benchmark above or use the
[Engine performance baseline workflow](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/engine-performance.yml)
to collect samples for the exact source and environment you want to compare.
Keep the generated reports with that run's artifacts.

Shared analysis reuses immutable source facts and readiness classifications for
one inspection. Mutable provider ASTs and global caches are not shared. Compare
canonical inspection bytes as well as timings when changing this code.
