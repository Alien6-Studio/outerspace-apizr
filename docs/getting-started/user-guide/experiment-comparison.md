# Compare two experiment runs

“My ROC AUC changed. What else changed between these runs?”

Start with `apizr experiment list`, choose Run A and Run B, then use
`apizr experiment diff RUN_A RUN_B`. The report separates **Material evidence
differences** (code, data, parameters, randomness, environment, serving) from
**Observed result differences** (status, metrics, outputs).

## Try it with core Python

These two small workloads require no data-science framework. The `run` commands
execute trusted code with host access, as described in the [run guide](experiment-runs.md).
The `diff` commands only read the validated local experiment store.

<!-- experiment-diff:guide -->
```sh
cat > compare_train.py <<'PYTHON'
max_depth = 8
score = 0.91
PYTHON
apizr experiment inspect compare_train.py
A=$(apizr experiment run compare_train.py --metric roc_auc=score --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
cat > compare_train.py <<'PYTHON'
max_depth = 12
score = 0.92
PYTHON
B=$(apizr experiment run compare_train.py --metric roc_auc=score --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment diff "$A" "$B"
rm compare_train.py
apizr experiment diff "$A" "$B" --format json > comparison.json
```

The text report includes the complete Run and Plan SHA-256 identifiers for both
sides. Its parameter section shows `max_depth` intended and observed values, 8
and 12; its metric section shows `roc_auc` 0.91 and 0.92 with delta `+0.01`.
The code identity also changes because this example changes the source bytes.
The final comparison succeeds even though `compare_train.py` has been deleted.

Apizr identifies recorded differences; it does not prove which one caused the metric change.

## Read the report

| State | Meaning in A → B |
| --- | --- |
| `same` | Known comparable recorded evidence matches. |
| `changed` | Known comparable recorded evidence differs. |
| `added` | Evidence is recorded only in B. |
| `removed` | Evidence is recorded only in A. |
| `unknown` | The available evidence does not establish equality or a difference. |

Added and removed describe **evidence membership**, not whether a workload
actually computed a metric or created a model. Swapping the runs swaps these
states and negates comparable numeric deltas. Comparing a Run with itself keeps
unknown evidence unknown and produces zero deltas for numeric metrics.

Counts describe individual comparison facets, with Plan and Run evidence counted
separately. Source identity and serving identity are separate facets. Exact Plan
identity is context; it does not replace the field comparisons. Timing is excluded
from the counts because different execution timestamps alone do not describe a
material change. Repeated runs can therefore report “No material recorded
differences among comparable evidence” while still displaying unknown facts.

Matching recorded evidence does not prove the workloads are reproducible or
equivalent in every unobserved respect.

## Intended and observed evidence

- **Code:** compare the full source identity, including source and executable
  digests, reference, module and capability. Optional unknown subfields stay visible.
- **Data:** match logical names and retain planned A, observed A, planned B and
  observed B. Planned selection can be added/removed or match exactly. Only two
  known observed digests can establish equal/different runtime content. Identical
  remote URIs establish a reference match, not verified content.
- **Parameters:** compare intended and observed values separately. Missing runtime
  values remain unknown; a separate membership field records added/removed runtime
  evidence. Known JSON `null` is comparable; an unknown origin is not. JSON object
  order does not matter, array order and canonical numeric types do.
- **Randomness:** match `(provider, name)` independently in Plan and Run evidence.
  A declared seed is never promoted to a runtime observation. Unknown seeds and
  accelerator determinism remain unknown.
- **Environment:** separate Plan evidence from the recorded worker environment.
  Compare implementation, Python version, platform, architecture, canonical package
  names/versions/origins and lock/config artifacts. Missing scalar values or unknown
  versions/digests do not establish equality. No package metadata is queried.
- **Serving:** known capability IDs can match, differ, be added or be removed;
  two absent IDs are unknown.

## Observed results

Status always shows both outcomes, including failed or cancelled Runs. Metrics
match by name and retain full bounded JSON values and units. Numeric deltas are
`B - A` only for `int`/`float` scalars with equal units and a finite difference.
Booleans, nulls, strings and structured metrics have no delta; units are never
converted. Canonical `1` and `1.0` are different recorded values even if their
delta is zero. No percentage, quality ranking or causal explanation is inferred.

Outputs match by name. Their complete reference, digest, size and media-type
evidence is compared; a metadata change remains visible when content digests
match. Diff does not reopen, hash, deserialize or evaluate a model.

## Store and machine interface

`show RUN` inspects one exact Run; `diff RUN_A RUN_B` compares two validated
RunRecords using the same content-addressed store. Both accept full SHA-256 IDs
or unique lowercase prefixes of at least 12 characters. Use `--store PATH` for
another store; the default is `.apizr/experiments/v1` under the current directory.
Corrupt, missing or ambiguous evidence is refused with exit code 2. Valid
comparisons return 0 even when evidence differs.

`--format json` emits the immutable
[`apizr.experiment-diff/v1` contract](../../specs/apizr-experiment-diff-v1.schema.json).
Typed category records preserve underlying evidence and bind both full Run and
Plan digests. This derived view does not replace the original records. Human
rendering limits long values and sections explicitly; JSON retains all evidence
within its own bounded item and byte limits.

Comparison performs no execution, source analysis, artifact reads, network access
or package inspection. The human report always ends with:

> These are recorded evidence differences. Apizr does not establish which difference caused an observed result change.
