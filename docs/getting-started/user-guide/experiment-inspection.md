---
title: Inspect an experiment
description: Understand Python training scripts and notebooks without running them.
---

# Inspect an experiment (0.4.5 development)

Have a training script or notebook? `apizr experiment inspect` shows **Code, Data,
Parameters, Randomness, Environment, Metrics, Outputs and Serving** without
executing it. It reads the selected source, recognized local input files and
root-level environment specifications. It never imports your project or its
science frameworks, downloads data, installs packages or starts a worker.

This command is available from the `0.4.5` development checkout, not the published
0.4.4 package. Install that checkout into an isolated environment with
`python -m pip install .`. Python inspection needs only the core. For notebooks,
use `python -m pip install '.[notebook]'` in the same checkout. The existing
`outerspace-apizr[notebook]` extra provides notebook conversion; pandas, NumPy and
scikit-learn are not required for lexical recognition.

## Try a small script

These setup commands create two example files in your current directory. The
inspection command then reads them without running the script:

<!-- experiment-inspection:example -->
```sh
printf 'amount,fraud\n10,0\n' > train.csv
cat > example.py <<'PY'
import pandas as pd
from sklearn.metrics import roc_auc_score

learning_rate = 0.05
training = pd.read_csv("train.csv")
validation = pd.read_csv(DATA_PATH)
roc_auc_score(labels, predictions)

def predict(amount: float) -> float:
    return amount
PY
apizr experiment inspect example.py
apizr experiment inspect example.py --format json
```

Data includes the SHA-256 and size of `train.csv`, together with an unresolved
dynamic reference. Parameters includes `learning_rate`. Metrics identifies
`roc_auc_score`, with no metric value. Serving retains `python:example:predict`
and Apizr's source-local readiness. The undefined names do not need runtime
values for inspection to complete.

For your own files:

```sh
apizr experiment inspect train.py
apizr experiment inspect fraud_detection.ipynb --format json
apizr experiment inspect src/train.py --root . --module-name research.train
apizr experiment inspect train.py --input training=data/train.csv
apizr experiment inspect train.py --max-input-bytes 10485760
```

Exit **0** means inspection completed, including partial, unknown or uncontrolled
evidence. Exit **2** means invalid arguments or a source that cannot be inspected.
Interface readiness does not change this exit policy.

## Read the evidence

| Section | Evidence and deterministic state |
| --- | --- |
| Code | `captured` after successful bounded parsing; portable reference, kind, module, source SHA-256, IR/readiness identities and source diagnostics. Notebook export and signal digests are separate. |
| Data | `captured` only when at least one selected input has been fingerprinted, every selected input has a digest and no diagnostics remain. Otherwise `partial` when references/diagnostics exist, or `unknown`. Remote content is always unverified. |
| Parameters | `captured` for direct literal assignment candidates with no unresolved assignments; `partial` with diagnostics; `unknown` with neither. These candidates are not authoritative runtime parameters. |
| Randomness | `captured` for known static controls without diagnostics; `partial` for dynamic/conflicting controls or framework determinism uncertainty; explicit unseeded controls take precedence as `uncontrolled`; absence is `unknown`. |
| Environment | `partial` for root-level specifications, versionless framework import candidates or diagnostics. Runtime Python/platform/package versions are never borrowed from the inspector. No evidence means `unknown`. |
| Metrics | Static metric calls or diagnostics give `partial`; absence gives `unknown`. Calls never establish observed metric values. |
| Outputs | Static output paths or diagnostics give `partial`; absence gives `unknown`. Existing output files are not opened or fingerprinted. |
| Serving | `partial` when canonical callable assessments exist; otherwise `unknown`. Individual interface readiness and reasons retain their existing meaning. Neither state establishes operational model serving. |

`captured` describes the stated evidence, not scientific reproducibility.
`not_applicable` is reserved in the state vocabulary; v1 never derives it because
absence of static detection cannot prove non-applicability. Inconsistent supplied
states, including an unjustified `not_applicable`, are rejected. No overall score
is computed.

The human report shows a bounded sample and points to JSON for the complete
evidence. It shows dynamic references without guessing their values.

## What is recognized

Inputs, randomness, environment specifications, metric calls and output paths
compose the [existing evidence producers](../../architecture/experiment-evidence-v1.md).
No second framework resolver is introduced. An explicit `--input` declaration
keeps `declared` reference provenance and `static` content provenance when hashing
succeeds. It does not prove that a dynamic Python expression resolves to that file.

Parameter candidates are direct module/code-cell `name = literal` and annotated
assignments. Finite JSON literals, signed numbers and nested lists/tuples/string-key
objects are accepted within the existing experiment-value bounds. Repeated and
chained assignments retain separate source occurrences. Expressions, environment
variables, calls, destructuring, attribute assignments and nested control-flow
assignments are not evaluated. Constructor keyword parameters are not extracted
in v1; `random_state` keywords belong to the existing Randomness producer.

Literal strings are explicitly inspected source content and are included in
parameter candidates. There are no secret-name heuristics. The JSON does not
contain whole Python source, cell text, notebook JSON, dataset contents or function
bodies. Location references and canonical readiness evidence identify findings.

## Root, bounds and notebook locations

The default root is the source's parent. `--root` selects another explicit root;
the source must be inside it. Local data paths and environment specifications are
relative to that root, independently of the shell's current directory. The root's
absolute host path is never serialized. Symlinks and non-regular source/input files
are refused by the existing descriptor-based file readers.

Python source is limited to 1 MiB, 100,000 AST nodes and depth 128. Notebook input
is limited to 16 MiB and 1,024 cells in nbformat 4, with the same aggregate Python
code bounds. Each code cell must parse independently as ordinary Python. Magics,
shell commands and exporter transformations that change its AST are refused.
Older notebook formats must first be converted by the user to nbformat 4.

Local inputs default to at most **1 GiB per file**, configurable with
`--max-input-bytes` up to 1 TiB, with at most 256 selections. Existing environment
specification bounds apply: 32 matching root-level files, at most 4,096 root entries,
and 16 MiB per specification. Existing producer result bounds remain enforced.
Inspection JSON is limited to 16 MiB; no evidence is silently truncated to fit.

Notebook signals use deterministic code-cell concatenation in document order.
Imports and rebinding span cells. Each location retains zero-based `cell_index`
(including markdown/raw cells), zero-based `code_cell_index`, and one-based
`cell_line`. `line` is the one-based analysis representation line, and `column`
is a zero-based UTF-8 byte offset. Python uses ordinary source lines.

The existing notebook exporter and Capability IR remain unchanged. An AST equality
check maps its nodes back to the code cells without trusting `In[...]` comments.
Raw notebook and transformed/exported digests may change when execution counts,
markdown or stored outputs change; the separate `signal_digest` ignores those
items. Stored outputs/counts never establish a metric, output or executed state.

## Python API and existing repository evidence

```python
from apizr.experiments.inspection import inspect_experiment
from apizr.experiments.reporting import inspection_bytes

inspection = inspect_experiment("train.py")
payload = inspection_bytes(inspection)
```

`ExperimentInspection` lives in `apizr.experiments.inspection_model`. Its version is
`apizr.experiment-inspection/v1`; the [JSON Schema](../../specs/apizr-experiment-inspection-v1.schema.json)
is regenerated with `python scripts/export_experiment_schemas.py`. It embeds
existing producer records and canonical `Source`, capability entries and
`ReadinessReport`, with IR/readiness digests. `locations` contains JSON pointers to
those records. No experiment-specific capability identity is introduced.

Applications that already hold complete repository artifacts can enrich Serving:

```python
from apizr.experiments.inspection import enrich_serving

enriched = enrich_serving(
    inspection, catalog=catalog, graph=graph, readiness=repository_readiness
)
```

This explicit API validates the supplied Catalog/Graph/report binding and matches
the inspected source reference, module, bytes and IR/readiness identities exactly.
It uses existing readiness detail views and selection-scoped required evidence;
an unrelated ambiguity cannot silently downgrade the selected function. It never
rescans a repository. Current Catalog source units are Python-only, so notebook
inspection remains source-local. Missing, stale or incompatible artifacts are
refused.

**Inspection** asks what evidence is visible. **Readiness** asks whether a callable
satisfies Apizr's interface/execution contract. An **Experiment Run** records what
was observed during actual execution. Inspection never means the experiment ran.
It can feed a later Experiment Plan without inventing execution intent. Run,
history, comparison and experiment exposure commands are not part of this feature.
