# Seeds and environment evidence

## Seeds are evidence, not guarantees

Consider this source:

```python
import numpy as np

rng = np.random.default_rng(42)
```

Apizr can see the fixed RNG seed in the source. It cannot conclude that every
library, thread, GPU kernel or external system will behave deterministically.
Same seed + same packages is useful evidence. It is not a proof of bit-for-bit
reproducibility.

The Python API inspects supplied source without importing NumPy:

<!-- executable-randomness-example -->

```python
from apizr.experiments import discover_randomness

result = discover_randomness(
    "import numpy as np\nrng = np.random.default_rng(42)",
    source_reference="train.py",
)
controls = result.controls
assert controls[0].provider == "numpy"
assert controls[0].name == "random.default_rng"
assert controls[0].value == 42
assert controls[0].origin.value == "static"
assert result.relevant_distributions == ("numpy",)
```

A static control describes syntax, including syntax inside a function that may
never run. It is not an observation that the seed was applied. Explicit callers
can place `result.controls` in `ExperimentPlan.randomness`.

## Recognized controls

| Statically bound callable | Provider | Control name | Fixed values recognized |
| --- | --- | --- | --- |
| `random.seed` | `python.random` | `seed` | Signed 64-bit integer, finite float, bounded string |
| `numpy.random.seed` | `numpy` | `random.seed` | Integer from 0 through 2³² − 1 |
| `numpy.random.default_rng` | `numpy` | `random.default_rng` | Nonnegative signed 64-bit integer |
| `sklearn.<callable>(random_state=...)` | `sklearn` | `<callable>.random_state` | Integer from 0 through 2³² − 1 |
| `torch.manual_seed` | `torch` | `manual_seed` | Signed 64-bit integer |
| `tensorflow.random.set_seed` | `tensorflow` | `random.set_seed` | Signed 64-bit integer |

Unambiguous import aliases and from-import aliases work. Qualified NumPy and
TensorFlow modules and sklearn submodules are recognized. Rebinding, parameter
shadowing, star imports, conditional imports and calls before their import cannot
grant framework authority. Unsupported bindings produce no control; source import
candidates can still be reported. Generic type-parameter scopes are ignored.
There is no project import resolution: lexical import identity does not prove
which installed module Python would load.

One positional seed or its named keyword (`a` for stdlib, `seed` otherwise) is
supported. Extra arguments, including an explicit stdlib `version`, leave the
value unknown. Sklearn recognition observes the named keyword; it does not check
an installed version's callable signature. Other sklearn arguments are allowed;
`**kwargs` alongside `random_state` makes its value uncertain.

```python
from sklearn.ensemble import RandomForestClassifier

RandomForestClassifier(
    n_estimators=200,
    random_state=42,
)
```

This records `sklearn / ensemble.RandomForestClassifier.random_state = 42`
without importing sklearn. Different callables retain different identities.
Repeated observations of one control collapse if equal. Conflicting values, or
fixed and dynamic values together, become unknown; first/last occurrence never
wins. Line numbers belong only to diagnostics. Different generator instances
created through the same API are therefore conservatively combined.

`None` and an omitted seed are unknown/uncontrolled. Names, arithmetic, environment
lookups and function results are not evaluated. Signed numeric literals are
supported; booleans, bytes, seed arrays and RNG objects are outside this producer.
The canonical contract's signed 64-bit integer and bounded string limits also
apply where a framework accepts larger values. Those unsupported values become
unknown, never truncated. Fixed Torch or TensorFlow seeds additionally produce
`accelerator_determinism = null`, origin `unknown`, and a diagnostic. No CPU,
GPU, CUDA, kernel or cross-version determinism is established.

The API scope follows the documented [stdlib seed types](https://docs.python.org/3/library/random.html#random.seed),
[NumPy generator construction](https://numpy.org/doc/stable/reference/random/generator.html),
[PyTorch manual seed](https://docs.pytorch.org/docs/stable/generated/torch.manual_seed.html)
and [TensorFlow global seed](https://www.tensorflow.org/api_docs/python/tf/random/set_seed).
Apizr deliberately recognizes a smaller bounded literal subset.

## Selected runtime environment

`capture_runtime_environment(distributions=("numpy", "scikit-learn"), root=root)`
observes the **current trusted process**. It returns `EnvironmentResult` with
canonical `EnvironmentEvidence` and producer diagnostics. A future execution
caller can place its evidence in `ExperimentRun.environment`; this API neither
executes an experiment nor automatically creates a Run.

An illustrative summary could read:

```text
Python: cpython 3.14.8
Platform: darwin
Architecture: arm64
outerspace-apizr: <installed version>
numpy: <installed version or unknown>
scikit-learn: <installed version or unknown>
uv.lock: sha256:<exact bytes digest>
```

Implementation comes from `sys.implementation.name`; Python version consists of
major, minor and micro with `aN`, `bN` or `rcN` for prereleases. Platform is
`sys.platform`, and architecture is the actual `platform.machine()` value,
without OS-based inference or GPU probing. An unavailable/invalid fact is unknown.
The optional architecture field is omitted when absent in existing v1 payloads.

Apizr uses installed distribution metadata for its own version and at most 64
explicitly selected names. Names are normalized; duplicate normalized selections
are rejected before observation. Selecting Apizr explicitly does not add it twice.
Missing packages have `version=None, origin=unknown` and a diagnostic. Unreadable
or invalid version metadata also remains unknown. There is no full installed
package enumeration, target-package import, pip/uv invocation, resolution,
installation, subprocess or network access.

`discover_randomness(...).relevant_distributions` reports only this source import
mapping, independently of whether a randomness call was recognized:

| Import root | Distribution candidate |
| --- | --- |
| `numpy` | `numpy` |
| `pandas` | `pandas` |
| `sklearn` | `scikit-learn` |
| `joblib` | `joblib` |
| `torch` | `torch` |
| `tensorflow` | `tensorflow` |

Conditional and star imports can establish a syntactic candidate, never an
installed version or callable authority. Relative imports are excluded. Unknown
import roots are not guessed. Passing these candidates to runtime capture is an
explicit caller choice.

Apizr does not snapshot environment-variable values into experiment evidence.
It does not hash those values either, read `.env`, or serialize hostname, home,
PATH, credentials or device-selection environment variables.

## Environment specification identities

`discover_environment_specs(root)` returns static environment evidence suitable
for a Plan. Runtime capture with `root=root` observes the same file families with
runtime provenance. Omitting `root` performs no specification discovery.

Only the supplied root is scanned, with case-sensitive names:

- `uv.lock`, `poetry.lock`;
- basenames beginning with `requirements` and ending with `.txt` or `.lock`;
- `environment.yml`, `environment.yaml`, `conda.yml`, `conda.yaml`.

There is no recursion, parsing, dependency resolution or format inference. At
most 32 matching files and 4096 root entries are admitted; exceeding either
bound returns an explicit diagnostic and no partial selection. All names must
satisfy the existing portable-reference and 128-character logical-name rules.

Each regular file receives its relative name/reference, exact byte size and
SHA-256. The shared input fingerprint reader streams bytes using descriptor-relative
access, refuses symlinks/special files and discards digests if a file changes
while being read. Contents and absolute paths are not emitted. Default file size
is 16 MiB; callers may supply the existing `FingerprintPolicy`. Unverified files
retain a diagnostic, unknown content and no digest/size. There is no aggregate
atomic filesystem snapshot claim.

Static artifacts have `origin=static, content_origin=static`; successful runtime
observations have both origins `runtime`. Plan/Run origin validation remains
strict. Changing lock bytes changes the artifact digest and a Plan that includes
that static evidence. Changing an observed package version changes Run identity,
without changing its bound Plan.

Recording `uv.lock`'s SHA-256 establishes the identity of that file's bytes. It
does not prove the environment was installed exactly from that lock unless later
execution evidence establishes that relationship.

## Bounds and diagnostics

Source analysis admits at most 1 MiB, 100,000 AST nodes and depth 128, shared with
input discovery. Results contain at most 128 controls, 512 diagnostics and six
versionless package candidates. Controls sort by `(provider, name)`; diagnostics
sort by source, line, column and code. Source/result limit refusal returns no
partial controls. Invalid source identities and rejected literal values are not
echoed in diagnostics.

Randomness diagnostic codes are `dynamic_randomness_control`,
`uncontrolled_randomness`, `unsupported_randomness_literal`,
`unsupported_randomness_arguments`, `randomness_control_conflict`,
`randomness_control_name_invalid`, `randomness_source_invalid`,
`randomness_discovery_limit` and `framework_determinism_unknown`.

Environment diagnostics sort by name and code and are bounded to 128. They use
`environment_specs_limit`, `environment_specs_unreadable`,
`environment_spec_reference_invalid`, `environment_value_unavailable`,
`environment_package_missing`, `environment_package_unreadable`, and the existing
[input fingerprint diagnostics](experiment-inputs.md) for individual files.

See [Experiment evidence v1](../architecture/experiment-evidence-v1.md) for the
canonical contracts and schema links. These APIs add evidence producers; no
experiment CLI, metrics collection, execution, history store or comparison is
implemented here. Evidence differences establish neither reproducibility nor
causality.
