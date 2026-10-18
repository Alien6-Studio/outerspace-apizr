# Engine baseline and history optimization — 0.4.6 development

Evidence for #319 and #320. Baseline engine: `3f02a13866a40a2a415906bb0b87ba880a184d72`. Optimized engine:
this change, identified by the production-file hashes in `after.json`. Both runs
use the same benchmark method, fixtures, locked environment and interpreter.
`before.json`/`after.json` retain every sample, profile call counts, source hashes,
and canonical fixture manifests; all three history manifests match byte for byte.
The benchmark was introduced during this work, so both reports explicitly retain
their dirty-source flag. Its later metadata/reporting additions do not change the
measured operations. The baseline source hashes identify the unchanged pre-work
engine. The optimized report identifies the final implementation.

- Python: `3.12.13 (main, Jul 23 2026, 14:33:47) [Clang 22.1.3 ]`.
- Platform: `macOS-27.0.1-arm64-arm-64bit`; machine `arm64`; logical CPUs: 16.
- Runner: local, not a hosted-CI or billing measurement.
- Method: three sequential samples per case, median reported; no cache eviction.
  Fixture construction and cProfile runs are outside the timed samples.
- New publication uses the real durable API. History fixtures share one v1 Plan;
  SDK entry/logging/finalization also exercise v2 capture separately.
- Timings include noise and process startup where specified. Small startup-heavy
  editor samples can move in the opposite direction to in-process history costs.
  These results do not establish a cross-platform latency guarantee.

## Median timings

| Operation | Before (ms) | After (ms) | Change | Outcome |
| --- | ---: | ---: | ---: | --- |
| `import_apizr` | 15.0280 | 21.3685 | +42.2% | success |
| `import_tracking` | 163.1432 | 151.3315 | -7.2% | success |
| `cli_version` | 59.8495 | 50.4188 | -15.8% | success |
| `inspect_ipynb` | 379.7040 | 403.1801 | +6.2% | success |
| `inspect_py` | 1174.4812 | 1190.7984 | +1.4% | success |
| `digest_0` | 0.0952 | 0.1136 | +19.4% | success |
| `digest_1048576` | 0.4992 | 0.4820 | -3.4% | success |
| `digest_16777216` | 6.3390 | 6.3147 | -0.4% | success |
| `publication_empty_store` | 2.6622 | 2.5985 | -2.4% | success |
| `sdk_0_entry` | 1.0282 | 0.9133 | -11.2% | success |
| `sdk_0_per_value` | 0.0004 | 0.0004 | +0.2% | success |
| `sdk_0_exit` | 1.4408 | 1.4490 | +0.6% | success |
| `sdk_256_entry` | 1.0000 | 0.8760 | -12.4% | success |
| `sdk_256_per_value` | 0.0064 | 0.0063 | -0.2% | success |
| `sdk_256_exit` | 10.2517 | 10.2781 | +0.3% | success |
| `history_10_list` | 16.2402 | 2.0029 | -87.7% | success |
| `history_10_show` | 10.9107 | 2.4415 | -77.6% | success |
| `history_10_diff` | 23.3883 | 3.1758 | -86.4% | success |
| `editor_capabilities` | 199.7997 | 189.1545 | -5.3% | success |
| `editor_experiment_list` | 224.0236 | 193.7633 | -13.5% | success |
| `editor_experiment_show` | 216.5223 | 196.7193 | -9.1% | success |
| `editor_experiment_diff` | 232.3405 | 194.4397 | -16.3% | success |
| `history_1000_list` | 1716.4279 | 169.9186 | -90.1% | success |
| `history_1000_show` | 986.5929 | 155.4769 | -84.2% | success |
| `history_1000_diff` | 2163.9110 | 183.0215 | -91.5% | success |
| `history_10000_list` | 4.1581 | 3.5749 | -14.0% | store_limit |
| `history_10000_show` | 3.7187 | 3.4946 | -6.0% | store_limit |
| `history_10000_diff` | 3.4884 | 3.5079 | +0.6% | store_limit |

`store_limit` at 10,000 Runs is the expected production refusal, not a successful
throughput result. Admission ceilings remain 4,096 entries and 64 MiB. Reports
must never relabel the refusal time as successful list/show/diff latency.

## Profile evidence at 1,000 Runs

| Operation | Python function | Before calls | After calls |
| --- | --- | ---: | ---: |
| list | `serialization.py:read_plan` | 1 | 1 |
| list | `serialization.py:read_run` | 1000 | 1000 |
| list | `serialization.py:plan_bytes` | 5001 | 0 |
| list | `serialization.py:run_bytes` | 4000 | 0 |
| list | `json.py:encode` | 9002 | 1002 |
| show | `serialization.py:read_plan` | 1 | 1 |
| show | `serialization.py:read_run` | 1000 | 1000 |
| show | `serialization.py:plan_bytes` | 3003 | 2 |
| show | `serialization.py:run_bytes` | 3001 | 1 |
| show | `json.py:encode` | 6005 | 1005 |
| diff | `serialization.py:read_plan` | 2 | 1 |
| diff | `serialization.py:read_run` | 2000 | 1000 |
| diff | `serialization.py:plan_bytes` | 6006 | 0 |
| diff | `serialization.py:run_bytes` | 6002 | 0 |
| diff | `json.py:encode` | 12040 | 1033 |

The former hot path decoded each artifact, then repeatedly revalidated nested
models and serialized them through record construction, summary and comparison
admission. The new reader decodes and verifies canonical bytes once per artifact,
checks the Run-to-Plan binding, and assembles the immutable record. Plans remain
cached only inside the bounded iterator. The public show serializer still
revalidates its selected record; no public admission gate is disabled. Diff now
selects both identities in one complete validation, rather than scanning twice.
`records` generator call counts also include iterator resume/completion calls;
`read_plan`/`read_run` identify actual JSON decodes.

Readable cumulative profiles for both sizes and all three operations accompany
these reports. Binary profiles remain in local/CI evidence, rather than Git.

## Regression policy and reproduction

[Method and budgets](https://apizr.outerspace.sh/architecture/engine-performance/) distinguish
informational wall-time tolerances from blocking artifact-admission, traversal,
canonical-output, corruption and resource-budget regressions. Initial timing
review threshold: twice each baseline median plus 50 ms, on the same fixture and
environment. No shared-runner timing failure is inferred from these local samples.

Run the retained benchmark with three repeats in separate checkouts/environments
of each implementation. When measuring the older commit, copy the new benchmark
module into its canonical script path; use that checkout's locked editable engine
and interpreter. Compare fixture/source hashes and outcomes before comparing times.
The discovery protocol and published package versions are unchanged by this work.
No publication or stable-branch workflow was invoked.
