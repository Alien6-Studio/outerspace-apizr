# In-process experiment evidence v2 (0.4.6 development)

The new `apizr.experiment-plan/v2` and `apizr.experiment-run/v2` contracts
describe explicit captures inside an existing process. The original v1 contracts
remain frozen: the CLI runner continues to produce v1 until its producer is
explicitly migrated. `read_plan` and `read_run` dispatch on `schema_version`,
refuse unknown versions and retain the exact canonical v1 bytes and SHA-256
digests. There is no automatic rewrite of stored records.

## Capture and observations

`CaptureIdentity` records a mode (`cli_run`, `sdk_session`, `decorated_call`,
`jupyter_cell` or `unknown`), a producer and its version, selected call parameter
names, an optional observed function binding and optional kernel cell evidence.
The Plan and Run must carry identical capture identities. This binds observed
call parameters to the selected function and prevents mixing unrelated captures.
These producer facts are known when intent is created; they do not claim that
the workload has completed.

`SourceEvidence` contains a v1 `SourceIdentity` only when exact source bytes have
been observed. In an interactive or unsaved session it instead records
`origin=unknown` and no identity. A missing file is never replaced by invented
source bytes or a digest of the function name.

`FunctionBinding` records the observed module and qualified name. An optional
`definition_id` distinguishes definitions within the process, including notebook
redefinitions; it is an opaque correlation id, not a content digest. A missing
`source_digest` means that definition's source content is unknown. Kernel-observed
`CellIdentity` records the available cell id, execution count and source digest.
Saved notebook identity and a live cell identity are distinct observations. An
unknown function or cell may not carry known-looking values.

`CallParameter` contains only an explicitly selected, bounded JSON value or an
unknown value with an optional bounded type name. It uses the same finite,
immutable value limits as v1; arbitrary objects are never pickled. The Run's
call parameter names must exactly match the capture selection. Ordinary explicit
parameters, inputs, randomness, environment, metrics and outputs retain v1's
provenance and size/count rules. A successful Run cannot carry failure diagnostics.

## Execution ids and final evidence identities

The producer assigns `execution_id` at capture start. It is a 32-character opaque
hex identifier for logging or cancellation while the capture is open. It is never
used as a canonical store filename or as proof of evidence identity. Once the
Run is finalized, `run_digest` is SHA-256 of its validated canonical bytes;
`plan_digest` binds it to the exact Plan. The final record must pass both schema
validation and `validate_run_binding` before publication.

## Compatibility and qualification

The v1 schema exports remain unchanged. The independent v2 exports live at
`docs/specs/apizr-experiment-plan-v2.schema.json` and
`docs/specs/apizr-experiment-run-v2.schema.json`. Regenerate them with
`scripts/export_experiment_schemas.py`. Frozen 0.4.5 store fixtures qualify
`list`, `show` and `diff`, canonical bytes and original digests. The installed
contract proof exercises both versions without optional or scientific SDKs.
