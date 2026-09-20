# Deterministic REST generator v1

The REST generator is the first consumer of Capability IR and Readiness. It
produces an ordinary JSON/value interface from their contracts. The historical
CodeAnalyzr → FastApizr → Dockerizr pipeline remains independent.

```text
source → Capability IR v1 → Readiness v1 → REST plan
                                            ↓
                          application + OpenAPI + manifest
```

## Boundary and versions

`apizr.generators.rest` contains typed plans, IR type lowering, static OpenAPI
construction, deterministic serialization, bundle rendering and exclusive output
handling. Its standalone runtime adapter is copied as source into the bundle.
The generator reads that adapter resource; it does not import FastAPI or import
or execute the user's source. The IR/readiness packages do not load the generator.

`apizr.rest/v1` versions the REST plan and manifest. The identifiers
`apizr.capability/v1` and `apizr.readiness/v1` remain independent and unchanged.
No REST fields are added to either upstream model.

`render(inspection, source, executable=None, select=None)` returns ordered artifact
bytes. `generate(inspection, source, output, ...)` writes those bytes exclusively.
The inspection is revalidated, including its IR/readiness digests and source
linkage. Source bytes must match the IR source digest. A notebook also requires
its exact exported Python bytes, matching `transformed_digest`. Assessment
identities, IR membership, source spans and effects must agree with the IR.
This is content binding, not authentication of an artifact producer.

## Eligibility and selection

The only eligibility authority is `assessment.can_generate_interface`. The
planner does not rerun readiness or analyze original Python source. Its only AST
parsing lowers the type expressions already declared in the IR.

By default, every callable assessment must be eligible. Conditional, unsupported
and ambiguous declarations produce actionable refusals with their readiness
codes. Explicit selection accepts capability names or full IR identities, then
requires every selected assessment to be eligible. Unknown or empty selections
are errors. Empty source is not an application. There is no unsafe override.

Unselected generator declarations can coexist with selected ready functions.
Selection cannot bypass module-wide initialization uncertainty already recorded
on those functions by Readiness.

A genuine boundary inconsistency was identified in [issue #39](https://github.com/Alien6-Studio/outerspace-apizr/issues/39):
renamed typing symbol imports could previously be ready although IR v1 does not
record the alias mapping. Readiness now marks those input meanings unresolved.
For example, `from typing import List as Sequence` does not establish a
self-contained `Sequence[int]` contract. Direct `List` imports and module-qualified
`t.List` retain their explicit member spelling. No source alias resolver is added
to the REST generator. This correction changes affected readiness decisions and
digests, not IR bytes or readiness model fields.

## HTTP and input contracts

Every capability uses `POST /capabilities/<name>`. Unknown effects do not justify
GET/PUT/DELETE inference. `/health`, `/openapi.json` and `/docs` are infrastructure
routes; a function named `health` remains `/capabilities/health`.

The request is a JSON object, including `{}` for a function without parameters.
Required fields follow the IR signature. Unexpected fields and invalid values
produce HTTP 422. Validation uses generated type descriptors, not user annotations
or `get_type_hints`.

| IR declaration | Request schema and Python value |
| --- | --- |
| `int` | JSON integer (booleans excluded); integral JSON numbers become Python ints |
| `float` | Finite JSON number, converted to a Python float; strings/booleans rejected |
| `str`, `bool`, `None` | JSON string, boolean or null respectively |
| No annotation, `Any` | Unconstrained finite JSON value |
| `list[T]` | JSON array, validated members, Python list |
| `dict[str, T]` | JSON object with validated values |
| `tuple[A, B]` | Array with fixed length and positional member schemas; Python tuple |
| `tuple[T, ...]` | Homogeneous array, Python tuple |
| `set[T]` | Unique array, converted to a Python set; members must be hashable |
| Bare containers | Their container shape with unconstrained members |
| Union / PEP 604 / Optional | Alternative schemas; Optional includes null |
| Literal | Scalar type and constant alternatives, distinguishing booleans from numbers |

JSON Schema does not express every Python storage constraint. Python float range
and set member hashability/equality are checked at the adapter boundary; invalid
values are rejected explicitly. No application-class inference, Callable adapter,
Annotated constraint interpretation or overload dispatch is introduced. The
implementation signature is the invocation contract; recorded overloads are not
merged into a new signature.

## Defaults and parameter kinds

An omitted optional field is not validated or forwarded. Python applies the
function's actual default, including the identity/state of mutable defaults. No
default expression is evaluated or copied by the generator. Defaults are not
inserted into OpenAPI as JSON values.

`x: int = None` permits omission but rejects explicit JSON null. An explicit null
requires a nullable declaration such as `int | None`, or an unconstrained input.

Positional-only fields become positional arguments. Positional-or-keyword and
keyword-only fields become named arguments. Python cannot encode a gap in a
positional call: with `f(a=1, b=2, /)`, supplying `b` requires explicitly supplying
`a` too. The adapter rejects such gaps with HTTP 422, and OpenAPI records this
constraint using `dependentRequired`. It does not inject an omitted default to
fill the gap. Trailing positional defaults may be omitted normally.

## Trusted runtime startup

Generation is static and offline: no target import, decorator/default/annotation
execution, network or subprocess. Starting the emitted application is the trust
boundary. Only run bundles whose source and dependencies you trust. Unknown
effects remain unknown; readiness is not execution approval or a sandbox.

Before source import, the adapter reads the executable bytes and verifies their
SHA-256 against the manifest's expected digest. For notebooks this is the exported
Python digest. Its loader compiles those exact verified bytes, bypassing cached
bytecode and avoiding a second source read. A mismatch fails startup before user
module execution. The manifest and adapter are not signed: replacing both source
and expected metadata is not prevented by this content-binding check.

Dotted identity is preserved by deterministic package paths under `source/` and
logical module registration at startup. Existing unrelated modules/packages with
the same names are rejected instead of silently reused. Choose a different
`--module-name` when a logical name conflicts with the runtime's loaded modules.
Relative/external dependencies are not copied or inferred; Readiness uncertainty
for them prevents generation.

After import, each selected symbol must be a Python function with matching
sync/async execution form, parameter names/kinds and required/default presence.
Generators, variadics, missing/non-callable symbols and contradictory signatures
fail startup. Verification reads function code/default presence; it does not read
or evaluate user annotations, including Python 3.14 deferred annotations.

## Responses and exceptions

Return declarations contribute documentation only. Statically representable
returns have a response schema; unknown returns use `{}`. No response model or
return-type validation is applied. Results undergo ordinary JSON serialization;
serialization failures are handled as server errors.

Async functions are awaited; sync functions run in the framework's thread pool.
Unexpected source or serialization exceptions produce a sanitized HTTP 500 with
`Internal server error`. Server logs retain diagnostic detail. Intentional FastAPI
`HTTPException` responses are preserved. Request validation errors use HTTP 422.

## OpenAPI and artifacts

OpenAPI 3.1 is constructed statically from the REST plan. It is not obtained by
starting the application. Paths, request/response schemas and operation IDs are
deterministic. Each operation carries `x-apizr-capability-id`; operation IDs are
full capability identities. The running application's `/openapi.json` serves the
same document, and `/docs` renders it through FastAPI's documentation interface.

A Python bundle contains:

```text
app.py
source/<logical module path>.py
source/<package>/__init__.py  # empty parent package files when needed
capability-ir.json
readiness.json
openapi.json
apizr-rest.json
requirements.txt
```

A notebook bundle additionally preserves the original bytes as `notebook.ipynb`.
The executable module is its exact inspected export. `requirements.txt` contains
only FastAPI, the repository's Starlette security floor, and Uvicorn. The adapter
needs no installed Apizr package. Arbitrary project dependencies are not inferred.

The manifest records its REST version, source record/digests, IR digest, readiness
digest, selected endpoint plans, executable location/digest and SHA-256 of every
other generated file. It excludes its own digest. The manifest can be hashed
independently by a consumer.

All JSON uses sorted keys, compact separators, UTF-8 and a final LF. Endpoints and
artifact names are sorted. No timestamps, hostnames, absolute paths or random IDs
are inserted. `app.py` is a common standalone adapter that loads its plan from the
manifest, avoiding interpreter-dependent Python literal rendering. The source's
original bytes are preserved, including any metadata already present in input.

**REST artifacts can later be externally attested; the generator does not
implement attestation.** No receipt, signature or Attest dependency is introduced.

## Output safety and verification

Rendering and validation complete before output writes begin. Existing non-empty
directories are refused. Canonical relative artifact paths, directory descriptors,
no-follow directory/file opens and exclusive file creation prevent traversal,
symlink escapes and overwrites. Output paths containing `..` or symlink components
are rejected. Writing requires directory-descriptor/no-follow filesystem support (tested on
Linux and macOS); unsupported hosts fail explicitly before writing. In-memory
rendering does not require these filesystem facilities. An I/O failure can leave a partial new bundle; it never authorizes
overwriting or deleting existing user files.

The reviewed fixture in `tests/fixtures/rest/v1/` covers sync/async, positional-only,
keyword-only/default parameters, lists, unions, Literal and documented returns.
Its OpenAPI and manifest bytes, including all artifact hashes, are checked on
Python 3.11–3.14. Hypothesis covers determinism, binding, validation, hostile
non-execution, source mutation and selection. REST coverage includes the standalone
runtime adapter, with a separate 90% branch-aware CI floor and strict Pyright.

Limits remain explicit: one source/notebook, no repository graph, class
capabilities, dependency inference, sandbox, effect inference, container output,
MCP, plugin system or legacy-generator migration. Historical [issue #28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28)
remains independent.
