# Metrics and output artifacts

## What did the experiment produce?

A data scientist needs named scores and the identity of saved results. Apizr
records these as `Metric` and `OutputArtifact` values in an `ExperimentRun`.
It also recognizes a bounded set of calls in existing Python source without
requiring changes to that source.

| Evidence available | Producer result | Meaning |
| --- | --- | --- |
| `roc_auc_score(...)` in source | `MetricSignal` | The statically bound call occurs in the program |
| An explicitly supplied observed score | `Metric` | The caller records that value with runtime origin |
| `joblib.dump(model, "artifacts/model.joblib")` in source | `OutputSignal` with a declaration | The call names a candidate output path |
| Bytes read from an explicitly selected regular file | `OutputArtifact` | Reference, exact SHA-256 and size observed at capture time |

A metric call seen in source is a signal. A metric value becomes Run evidence
only when its value is actually observed. File identity does not establish which
statement produced the file, whether a model is accurate, or whether an
experiment is reproducible.

## Explicit metrics

The caller gives the observation a name. `capture_metric` is a pure validated
constructor: it neither calculates a score nor sends it to a tracker.

<!-- executable-metric-example -->

```python
from apizr.experiments import capture_metric

roc_auc = capture_metric("roc_auc", 0.91)
classification = capture_metric("classification", {"precision": 0.87, "recall": 0.82})
fold_scores = capture_metric("fold_scores", [0.91, 0.89, 0.94])
latency = capture_metric("latency", 12.5, unit="ms")
assert roc_auc.origin.value == "runtime"
assert classification.value["precision"] == 0.87
```

These example numbers are explicit illustrative observations, not results
calculated by sklearn. Runtime origin identifies the caller-supplied observation;
the API cannot independently establish how the caller obtained it.

Values use the existing bounded `FiniteValue` contract: finite signed 64-bit
integers and floats, strings, booleans, JSON null, arrays and objects. Python
lists/tuples become immutable arrays, and dictionaries become immutable mappings.
Object key order does not affect canonical Run bytes; array order remains
meaningful. Containers are copied, so later changes to caller data cannot change
the evidence. Numeric strings remain strings; booleans remain booleans.

An optional `unit` is allowed only for an integer or float scalar. It is rejected
for strings, booleans, null, arrays and objects. Use separately named metrics when
observations require different units.

NaN, positive/negative infinity, arbitrary objects, exceptions, model instances,
DataFrames and ndarrays are rejected. The API never falls back to `repr()` or
stringification. Select and convert the specific observed values explicitly
before capture. Invalid capture arguments raise the redacted
`metric_capture_invalid` error.

There is no active run, global sink, database, background worker or tracker
connection. Repeated calls produce independent values. An `ExperimentRun` orders
metrics by name and rejects duplicate names.

## Existing sklearn code, without source edits

<!-- executable-results-discovery-example -->

```python
from apizr.experiments import discover_metrics, discover_outputs

source = """from sklearn.metrics import roc_auc_score, precision_score, recall_score
import joblib
roc = roc_auc_score(y_test, probabilities)
precision = precision_score(y_test, predictions)
recall = recall_score(y_test, predictions)
joblib.dump(model, "artifacts/model.joblib")
"""
metrics = discover_metrics(source, source_reference="train.py")
outputs = discover_outputs(source, source_reference="train.py")
assert [signal.name for signal in metrics.signals] == [
    "roc_auc",
    "precision",
    "recall",
]
assert outputs.signals[0].declaration.reference == "artifacts/model.joblib"
assert "value" not in metrics.signals[0].model_dump()
```

This parses the supplied source only. It does not execute calls, import a
framework, inspect output files, perform network access or start a process.
Arguments, predictions, variables and metric calculations are never evaluated.
The metric recognizer records call syntax even when its arguments would fail at
runtime; it does not validate the installed callable's signature.

The exact [sklearn metric](https://scikit-learn.org/stable/api/sklearn.metrics.html)
mapping is:

| Qualified callable | Semantic name |
| --- | --- |
| `sklearn.metrics.accuracy_score` | `accuracy` |
| `sklearn.metrics.precision_score` | `precision` |
| `sklearn.metrics.recall_score` | `recall` |
| `sklearn.metrics.f1_score` | `f1` |
| `sklearn.metrics.roc_auc_score` | `roc_auc` |
| `sklearn.metrics.mean_squared_error` | `mean_squared_error` |

`MetricSignal` contains `name`, `callable_name`, project-relative `source`,
one-based `line`, zero-based UTF-8 byte `column`, and `origin=static`. It has no
value. Multiple calls to the same metric retain separate positions and the same
semantic name; a source position is an occurrence, not a runtime metric identity.
The future execution layer can correlate these signals with actual observations.

Module imports, module aliases, from-imports and callable aliases are supported
when binding authority is unambiguous. Parameter shadowing, rebinding, writes to
module attributes, star imports, conditional imports and calls before the import
cannot grant authority. Supported nested scopes reuse the input/randomness
resolver; generic type-parameter definitions remain outside its scope. A lexical
module name does not prove which installed module Python will load.

`MetricDiscoveryResult` contains ordered `signals`, redacted `diagnostics` and
`relevant_distributions`. A recognized metric signal contributes only the
versionless candidate `scikit-learn`. There is no installed-version lookup.
Ambiguous or unsupported bindings yield no signal rather than a guessed metric.

## Candidate outputs and explicit selection

The static output recognizer supports only
[`joblib.dump`](https://joblib.readthedocs.io/en/stable/generated/joblib.dump.html),
including its safe module/from-import aliases. A literal second positional
argument or literal `filename=` keyword yields an `OutputSignal`. Its declaration
initially uses that reference as the logical name. The caller can choose a shorter
or more meaningful name explicitly:

```python
from apizr.experiments import OutputDeclaration, parse_output_declaration

selected = OutputDeclaration(name="model", reference="artifacts/model.joblib")
assert parse_output_declaration("model=artifacts/model.joblib") == selected
```

The pure parser does not trim names, resolve URIs or access files. It is suitable
for future CLI composition; #263 adds no experiment CLI. An optional bounded
`media_type` can be declared explicitly. Static discovery leaves it absent rather
than inferring a precise format from a filename suffix.

`OutputSignal` retains its declaration, `callable_name=joblib.dump`, source,
line/column and static origin. Repeated calls to one path remain separate signals.
`OutputDiscoveryResult` contains signals, diagnostics and the versionless `joblib`
candidate when an unambiguously bound serialization call is recognized, including
a call with an unresolved filename. No digest, size or runtime artifact is created.

Dynamic names, `Path(...)`, f-strings and variable references remain unresolved;
there is no constant propagation. Starred arguments, `**kwargs`, duplicate,
unknown or missing required arguments are refused. The documented `value`,
`filename`, `compress` and `protocol` argument positions are recognized, but their
runtime values are not interpreted. No attempt is made to enumerate additional
files a serializer might produce. Other serializers can use explicit declarations.

## Observe output bytes explicitly

Call `fingerprint_output(root, declaration, policy=...)` at the reviewed capture
point. The root locates the file; only its portable relative reference is retained.
The following self-contained example writes **opaque test bytes**, not a real
serialized estimator or the result of executing the source above:

<!-- executable-output-capture-example -->

```python
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from apizr.experiments import OutputDeclaration, fingerprint_output

with TemporaryDirectory() as directory:
    root = Path(directory)
    (root / "artifacts").mkdir()
    content = b"opaque illustrative model bytes"
    (root / "artifacts/model.joblib").write_bytes(content)
    result = fingerprint_output(
        root, OutputDeclaration(name="model", reference="artifacts/model.joblib")
    )
    assert not result.diagnostics
    artifact = result.artifacts[0]
    assert artifact.reference == "artifacts/model.joblib"
    assert artifact.digest == sha256(content).hexdigest()
    assert artifact.size == len(content)
    assert artifact.origin.value == "runtime"
```

`OutputCaptureResult.artifacts` can populate `ExperimentRun.outputs`;
`capture_metric` values populate `ExperimentRun.metrics`. Run construction,
binding and canonical serialization remain the existing explicit
[experiment contracts](../architecture/experiment-evidence-v1.md).
Static signals and declarations are rejected in those runtime collections.

`fingerprint_outputs(root, declarations, policy=...)` validates all selections,
names and policy before any file I/O. It orders artifacts by logical name and
rejects duplicate names. Two distinct names may identify identical bytes. A
missing or refused selection produces a diagnostic and no artifact; successful
selections in the same batch remain available. The batch is not an atomic snapshot
of multiple files.

The reader streams SHA-256 through descriptor-relative, no-follow traversal. It
refuses selected symlinks, symlink parents, directories, FIFOs, sockets and devices.
Size, inode/device and modification metadata are checked before and after reading,
including the selected path after reading. Detected changes discard the digest.
These checks do not establish immutable storage or protect against every privileged
filesystem adversary. Identical bytes under the same reference in different roots
produce identical artifacts; roots and file contents are never emitted.

The capture operation observes bytes at call time. The caller is responsible for
associating them with the correct run. #264 will own post-success execution
orchestration; #263 neither executes an experiment nor accepts a boolean claiming
that execution succeeded. Hashing does not prove that a statement produced the file.

Capturing `model.joblib` records its reference, size and SHA-256. Apizr does not
deserialize, copy, upload or register the model. Pickle, joblib, ONNX, Torch and
safetensors files remain generic opaque artifacts selected by the caller.

## Bounds and diagnostics

| Boundary | Limit |
| --- | --- |
| Source | 1 MiB, 100,000 AST nodes, depth 128 |
| Static signals / diagnostics | 256 / 512 per discovery result |
| Explicit output selections / Run metrics / Run outputs | 256 each |
| File fingerprint policy | 1 GiB default per file; configurable 1 byte through 1 TiB |
| Hash read chunk | At most 1 MiB, also constrained by remaining file allowance |
| Metric value | 64 KiB encoded JSON, depth 16, 4096 value nodes |
| JSON collection / string / object key | 1024 entries / 8192 / 256 characters |
| Name / media type / unit / relative reference | 128 / 128 / 64 / 1024 characters |

`FingerprintPolicy` is shared with input capture. Source/result limits refuse
the whole static result, so a truncated list is never presented as complete.
An invalid output declaration raises `explicit_output_invalid`; invalid or forged
capture selections/policies raise `output_selection_invalid` before observation.

Metric diagnostic codes are `metric_source_invalid` and `metric_discovery_limit`.
Output diagnostics distinguish `dynamic_output_reference`,
`nonportable_output_reference`, `unsupported_output_arguments`,
`output_name_required`, `output_missing`, `output_symlink`, `output_not_regular`,
`output_too_large`, `output_changed_during_read`, `output_unreadable`,
`output_source_invalid` and `output_discovery_limit`. A portable literal path
longer than the name limit needs an explicit short name. Diagnostics contain bounded
codes and admitted source positions/names, not rejected paths, source text, raw OS
errors or file payloads.

## Optional consumers later

MLflow, W&B, artifact stores and model registries may later consume explicitly
selected evidence through optional adapters. They are not core dependencies.
This feature adds no tracker session, model version, deployment state, experiment
runner, notebook execution, history store, comparison or serving bridge.
