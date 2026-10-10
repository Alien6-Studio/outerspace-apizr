# Experiment evidence v1

Before a run, Apizr can describe what you intend to execute. After a run, it can record what was actually observed. Those are separate artifacts.

An Experiment Plan describes intended experiment inputs and controls. An Experiment Run records observed execution evidence. Neither proves scientific causality or reproducibility.

| Before execution: Plan | After execution: Run |
| --- | --- |
| Selected notebook or Python source | Source actually used and exact Plan digest |
| Intended dataset/input identities | Observed dataset/input identities |
| Intended parameters and randomness controls | Effective parameters and observed randomness controls |
| Declared or static environment evidence | Observed environment evidence |
| Execution kind, policy digest and declared controls | Status, optional timing, metrics and output artifacts |

These are development contracts in `apizr.experiments`. This version supplies no
experiment command, inspector, runner, capture mechanism, comparison or history
store. Producers must supply evidence explicitly. Reading a Plan or Run does not
execute its source or resolve its references.

## An explicit Plan/Run pair

This fictional example demonstrates construction, not a captured execution. The
example digests identify placeholder content; a real producer must supply the
actual evidence. Runtime labels below describe the observations that producer
would need to collect.

```python
from apizr.experiments import (
    EvidenceOrigin,
    ExecutionIntent,
    ExperimentPlan,
    ExperimentRun,
    InputArtifact,
    Metric,
    OutputArtifact,
    Parameter,
    RandomnessControl,
    SourceIdentity,
    plan_digest,
    run_bytes,
    run_digest,
    validate_run_binding,
)

subject = SourceIdentity(
    kind="notebook",
    reference="notebooks/fraud_detection.ipynb",
    digest="a" * 64,
)
plan = ExperimentPlan(
    subject=subject,
    inputs=(
        InputArtifact(
            name="train",
            reference="data/train.csv",
            digest="b" * 64,
            size=4096,
            origin=EvidenceOrigin.STATIC,
        ),
    ),
    parameters=(
        Parameter(
            name="max_depth",
            value=8,
            origin=EvidenceOrigin.DECLARED,
        ),
    ),
    randomness=(
        RandomnessControl(
            provider="sklearn",
            name="random_state",
            value=42,
            origin=EvidenceOrigin.DECLARED,
        ),
    ),
    execution=ExecutionIntent(kind="trusted-notebook", policy_digest="c" * 64),
)

# A future execution producer would supply the actual observed values.
run = ExperimentRun(
    plan_digest=plan_digest(plan),
    subject=subject,
    status="success",
    effective_parameters=(
        Parameter(
            name="max_depth",
            value=8,
            origin=EvidenceOrigin.RUNTIME,
        ),
    ),
    metrics=(Metric(name="roc_auc", value=0.91, origin=EvidenceOrigin.RUNTIME),),
    outputs=(
        OutputArtifact(
            name="fraud-model",
            digest="d" * 64,
            size=1024,
            media_type="application/octet-stream",
            origin=EvidenceOrigin.RUNTIME,
        ),
    ),
)
validate_run_binding(run, plan)
canonical_run = run_bytes(run)
identity = run_digest(run)
```

The reviewed [Plan fixture](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/tests/fixtures/experiments/v1/plan.json)
and [Run fixture](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.5/tests/fixtures/experiments/v1/run.json)
include partial unknown input evidence and explicit environment/timing records.
They are fictional test values, not reported scientific results.

## Evidence origins and unknowns

`EvidenceOrigin` distinguishes `declared`, `static`, `runtime` and `unknown`.
A Plan permits declared, static and unknown input, parameter, randomness and
environment evidence. Execution controls are explicitly declared. A Run permits
runtime and unknown observations; scalar metrics, identified output artifacts,
timing and diagnostic records require runtime origin. No generic inferred-truth
state exists.

An unknown input may retain its selected logical name/reference, but its digest
and size are null. An unknown parameter or randomness value is null; a declared
or runtime JSON null is distinguishable by origin. Environment values and package
versions are null exactly when their origin is unknown. Empty collections mean
no records were supplied, not that capture established an empty environment.
Absent optional categories do not claim observation.

A captured seed/control is evidence of a declared or observed randomness control. It is not proof that execution is deterministic.

## Independent schemas and public values

The independent versions are `apizr.experiment-plan/v1` and
`apizr.experiment-run/v1`, exposed as `schema_version`. The schemas are generated
directly from the typed models:

- [Experiment Plan v1 JSON Schema](../specs/apizr-experiment-plan-v1.schema.json)
- [Experiment Run v1 JSON Schema](../specs/apizr-experiment-run-v1.schema.json)

All nested models are frozen and reject unknown fields. Python construction uses
strict types, tuples and `EvidenceOrigin` members; JSON input uses arrays and
origin strings via `model_validate_json`. Parameters copy caller containers into
immutable mappings and tuples. Producers create new values to add observations;
they do not mutate a Plan into a Run.

| Public value | Evidence carried |
| --- | --- |
| `SourceIdentity` | `kind` (`python` or `notebook`), relative `reference`, SHA-256 `digest`, optional `executable_digest`, logical `module`, exact opaque `capability_id` |
| `InputArtifact` | Logical `name`, optional relative reference/digest/size, explicit origin |
| `Parameter` | Logical name, finite bounded JSON value and origin |
| `RandomnessControl` | Parameter fields plus explicit provider/source |
| `EnvironmentValue` | Python implementation/version or platform value and origin |
| `PackageEvidence` | Canonical package name, version when known and origin |
| `EnvironmentEvidence` | Optional Python/platform values, explicit package inventory and lock/config `artifacts` |
| `ExecutionIntent` | Generic explicit kind, optional policy digest, declared controls |
| `Metric` | Logical name, finite numeric scalar, optional unit, runtime origin |
| `OutputArtifact` | Logical name, digest, optional known size/media type, runtime origin |
| `RunDiagnostic` | Bounded stable lowercase code and runtime origin; no traceback |
| `RunTiming` | Optional observed start/end/duration and runtime origin |

Capability identity is optional, including for notebooks without an inference
capability. If supplied, the exact logical identity participates in the Plan hash
and binding. Selecting a capability here does not establish Readiness or authorize
Exposure. Executable/transformed digests are optional explicit evidence; the
contract does not transform notebooks or compute source fingerprints.

Run status is `success`, `failed` or `cancelled`. A successful Run cannot contain
failure diagnostics. Failed/cancelled Runs may retain partial observations without
inventing metrics or exception details. Timing requires at least one observed
field, rejects naive datetimes, normalizes aware datetimes to UTC (`Z` in JSON),
and requires end at or after start and finite non-negative duration. Duration may
come from a monotonic clock and need not equal a wall-clock subtraction.

## Identity, ordering and limits

`plan_bytes` and `run_bytes` revalidate even unchecked `model_construct` or
`model_copy` values and nested records before dumping typed JSON. They sort JSON
object keys, emit UTF-8 with `ensure_ascii=False`, compact separators,
`allow_nan=False` and exactly one final newline. `plan_digest` and `run_digest`
return lowercase SHA-256 hex over those exact bytes. Canonical documents are
bounded to 4 MiB. No timestamp, UUID or host directory is automatically added.

Canonical serialization means the same artifact content produces the same bytes and digest. It does not mean separate experiment executions produce the same Run digest.

Named collections sort by name; randomness sorts by `(provider, name)`;
diagnostics sort by code. Package names normalize lowercase and runs of `-`, `_`
and `.` to `-`. Duplicate identities are rejected after normalization. JSON
object order is irrelevant, while arrays inside parameter values retain their
meaningful order. Integer and floating-point values retain their JSON number
representation; `1` and `1.0` need not have the same artifact identity.

| Boundary | Maximum |
| --- | --- |
| Inputs, parameters, metrics, outputs per artifact | 256 each |
| Randomness records, execution controls | 128 each |
| Packages, environment lock/config artifacts, diagnostics | 4096 / 64 / 32 |
| Logical names, versions, media types, diagnostic codes | 128 characters |
| Python/platform evidence values, metric units | 256 / 64 characters |
| Project-relative references, capability identity | 1024 / 512 characters |
| One parameter/control JSON value | 64 KiB, depth 16, 4096 value nodes |
| One JSON array/object, string, object key | 1024 entries / 8192 / 256 characters |
| Integer values, sizes | Signed 64-bit; sizes non-negative |

Text must be valid UTF-8. Logical text fields reject ASCII controls. Local references
must be portable project-relative paths: no absolute/drive paths, backslashes,
empty/dot/parent segments, NUL, URI schemes or home expansion. References do not
name registry objects or remote stores. Moving a project leaves identity unchanged
when its logical evidence stays the same. Arbitrary parameter strings are data,
not interpreted paths or Python expressions.

JSON Schema Draft 2020-12 describes structural validation. Cross-field origin and
status consistency, named uniqueness/order, UTF-8, portable-reference semantics,
recursive depth/node/byte budgets and Run-to-Plan binding are additionally enforced
by the typed API. Consumers must use that validation; schema validation alone is
not artifact admission. Regenerate schemas with:

```sh
uv run --locked python scripts/export_experiment_schemas.py
```

## Binding and trust boundaries

`validate_run_binding(run, plan)` validates caller-provided artifacts, the exact
Plan digest and the whole source identity, including absent/present capability,
logical reference/module and executable digest. It performs no external lookup.
Effective inputs, parameters and environment can differ from intent and remain
explicitly recorded without changing the Plan. A valid binding validates the
claim's internal consistency; it does not authenticate a producer or prove that
execution occurred. Use `run_bytes` to enforce the complete canonical byte budget
before handing the artifact to another system.

A Run can show that two executions used different inputs, parameters or environments. It does not prove that one of those changes caused a metric difference.

Matching metric names alone do not establish comparable experiments. There are no
causality, determinism or reproducibility flags. Producers must never put secrets
or machine-local absolute paths in parameter values. These contracts have no
credentials, authentication structure, secret store or arbitrary environment
variable map. Names such as `token_count` remain legitimate; the model does not
guess secrets from parameter names.

Experiment Run is an attestable artifact; it is not an attestation format.

The experiment domain depends on existing primitive contracts, bounded descriptor
access in `workspace.files`, and the
existing Pydantic runtime. No Attest, OCI, MCP, FastAPI, MLflow, W&B, DVC or
DS framework defines these values. External systems may consume their canonical
bytes later. The [package composition rule](code-organization.md#experiment-evidence)
records this dependency boundary.


## Additive input evidence in 0.4.5 development

#261 adds three optional fields to `InputArtifact`: `content_origin`, `format_hint`
and `uri`. Absent values are omitted from canonical serialization. Old valid v1
JSON still validates, and the original #260 Plan and Run golden bytes and SHA-256
values are unchanged. Both schema versions remain v1; their regenerated schemas
add optional properties without adding required fields.

`origin` describes the input/reference record. `content_origin`, when supplied,
describes how digest/size were established. A declared local selection can have
`origin=declared` and `content_origin=static` after fingerprinting. An absent
content origin retains legacy semantics: it makes no additional provenance claim.
`unknown` content requires absent digest and size; a known content origin requires
at least one of them. The producer always observes both digest and size together.
Plan evidence rejects runtime content origins, including environment artifacts;
Run observations permit runtime/unknown content origins. This prevents hiding a
runtime observation inside a declared Plan record or static evidence inside a Run.

`reference` retains its portable project-relative validation. `uri` is a separate,
mutually exclusive remote reference; see the exact URI and format vocabulary in
[experiment inputs](../guides/experiment-inputs.md). A remote URI is not evidence
of verified bytes. Future runtime producers may observe remote bytes independently;
#261 never fetches them. Format hints are canonical evidence, not parser guarantees.

JSON Schema describes structure. No schema alone establishes symlink safety,
exact-byte fingerprinting, changed-during-read detection or remote no-fetch.
These are responsibilities of the reviewed producer, with executable safety tests.


## Randomness and environment producers (#262)

`discover_randomness(source, source_reference=...)` returns bounded controls,
producer diagnostics and versionless distribution candidates. Controls use the
existing `(provider, name)` identity; repeated equal controls collapse, while
conflicting or dynamic values remain unknown. Import binding authority and bounded
AST parsing are shared with input discovery. Static presence, including presence
inside a function, does not establish execution. Torch/TensorFlow seed evidence
also retains unknown `accelerator_determinism`; no deterministic/reproducible
flag, score or causal conclusion is produced.

`capture_runtime_environment(distributions=..., root=...)` observes the current
trusted process's Python implementation/version, platform, machine architecture
and selected installed distribution versions, always including Apizr. It does not
import selected packages, enumerate all distributions, execute project source,
probe accelerators, invoke subprocesses, install packages or contact a network.
No environment-variable names or values are captured or hashed.

`EnvironmentEvidence.architecture` is an additive optional `EnvironmentValue`,
omitted when absent. It participates in the existing Plan/Run origin validators.
The v1 schema identifiers and original canonical golden bytes are unchanged.

`discover_environment_specs(root)` returns static file evidence; runtime capture
with an explicit root returns runtime observations. Both inspect only root-level
`uv.lock`, `poetry.lock`, `requirements*.txt`, `requirements*.lock`,
`environment.yml`, `environment.yaml`, `conda.yml` and `conda.yaml`. Admission is
bounded to 32 matches and 4096 entries. Each uses the same no-follow regular-file
fingerprint reader as input capture, with a default 16 MiB file limit. Successful
content origin matches the enclosing producer, static or runtime; failed content
remains unknown. Contents, absolute paths and arbitrary host state are not emitted.
A lock digest proves byte identity, not that packages were installed from it.

The [seeds and environment guide](../guides/experiment-randomness-environment.md)
defines exact callable/provider identities, accepted literals, import mappings,
bounds and diagnostics. These are producers for the existing contracts, not
new experiment execution, history, metrics or comparison orchestration.
