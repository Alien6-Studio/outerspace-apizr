# Shared static analysis qualification (#321)

Baseline: `ca456f406c6a9ff8c98ea3d75dc66332de01df9a`. Candidate: development
implementation based on `d8e9226e86bf36fc7ee8a1df5a6e2d1de1c75020`; the after
summary records a dirty checkout and hashes of the implementation files. The
candidate also contains provider selection (#310). No release version is changed.

Both runs use Python 3.12.13/macOS on the same shared machine and the existing
`benchmark_engine --repeats 3 --history-sizes 10`. Raw summaries retain every
sample, interpreter, platform, lock and fixture hashes. Timings are observations,
not isolated causal estimates or CI thresholds.

| Fixture | AST parses before → after | CLI median before → after |
| --- | ---: | ---: |
| fraud_detection.ipynb | 16 → 12 | 0.413 → 0.524 s |
| large.py (500 functions) | 1,010 → 7 | 1.219 → 0.483 s |

The notebook's observed time increased on this noisy sample (after samples
0.404/0.524/0.546 s); no notebook wall-time improvement is claimed. Its four
eliminated parses are a deterministic reduction in analysis work. The large
script's observed median fell about 60%. The identical `float` annotation is
classified once instead of parsed 1,000 times, and module initialization policy
is computed once instead of traversing the module for each function.

The parse inventories retain exact source SHA-256/caller counts and canonical
inspection hashes. The same AST-parse instrumentation was used before and after;
each instrumented inspection was compared byte-for-byte with an uninstrumented
inspection. The **before/after canonical hashes also match**:

| Fixture | Canonical inspection SHA-256 |
| --- | --- |
| fraud_detection.ipynb | `49b01300bfe9053b6c492885bed457776e6309163de05906da23af3bf6689608` |
| large.py | `241634a1929a754351e8ca6c9aeb27da11481a4b17f49d47d6a32841501ed66b` |

`SourceView` retains immutable source budget, digest and physical-line facts for
one inspection. Strict revalidation reuses facts only for identical source;
changed copies and JSON admission rebuild them. Provider requests still enforce
lowered bounds and every result is readmitted. Providers receive fresh mutable
trees on request; no tree or global mutable cache is shared across producers.
The built-in provider visits one privately owned tree and exports only immutable
evidence and locations. Readiness annotation keys retain structured declaration
ordering, including unsupported declarations.

New regression tests cover parse reuse, changed-source admission, tree isolation,
immutable metadata, per-producer overflow and existing source-location boundaries.
Existing golden and refusal tests remain authoritative. The security mutation
suite includes a mutant that removes the source-to-facts binding check.
