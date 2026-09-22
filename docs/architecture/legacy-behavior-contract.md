# Legacy behavior contract

**0.3 update:** the historical observations below remain as migration evidence.
Current CodeAnalyzr adds a separate class/method inventory (#5), and ambiguous
selected definitions/overload sets are now rejected before generation (#28).
See [current behavior](../modules/code-analyzr.md). Corresponding executable
characterizations have been updated to assert these deliberate changes.

This is an engineering characterization of the historical Apizr pipeline, based
on commit `f7286c3301f13b0b058ac64b1ef85b637c26ff05` (2026-09-20). It is the
reference for a later metadata-model migration, not a new capability schema.
The pipeline remains notebook/script → static AST metadata → generated FastAPI
application → dependency list/container. No Capability IR, MCP, decorator API,
plugin system, AI feature or attestation implementation is introduced here.

## Starting evidence

Before production changes, `uv sync --locked`, Ruff and Pyright passed. The
Python 3.14 suite passed **71 tests**, including the script/notebook deterministic,
offline and non-execution regressions. Branch-aware coverage was **56.07%**.
The complete lock audit passed with zero findings in runtime (72 entries),
development (28), documentation (30) and security tooling (29), with overlap
between groups. The existing **55%** coverage floor is unchanged.

The starting commit's [CI matrix](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35498289785)
passed tests and generated-container checks on Python 3.11, 3.12, 3.13 and 3.14.
[Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35498289889),
[CodeQL](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35498289770)
and strict documentation checks also completed successfully. These are results
for the starting commit, not substitutes for checking this PR.

## How to interpret the contract

- **SUPPORTED**: intentional behavior protected by tests.
- **EXPLICITLY REJECTED**: a deliberate, actionable rejection. A runtime crash
  does not qualify merely because the operation failed.
- **LEGACY OBSERVED**: reproducible behavior that must be reviewed before it is
  preserved or changed. Passing a characterization test does not endorse it.
- **FUTURE CANDIDATE**: useful behavior not implemented; explicitly deferred.

The executable corpus is
[`tests/fixtures/characterization/discovery.json`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/tests/fixtures/characterization/discovery.json)
and
[`annotations.json`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/tests/fixtures/characterization/annotations.json).
The first records source, classification and exact discovery expectations. The
second records static type representation separately from runtime validation or
failure expectations. They are test data, not a public product format.

## SUPPORTED

### Discovery and signatures

Module-level `def` and `async def` are discovered in **source order**. Private,
Unicode and long valid identifiers are retained (tested up to 209 characters).
Comments, blank lines, ordinary docstrings and formatting do not change the
metadata. Keywords inside comments/strings do not create functions. Function
bodies and class bodies are not recursively searched for callables.

Fixed positional, positional-only and keyword-only arguments, mixtures of these,
required arguments, defaults and all-default functions are represented. Metadata
marks default presence, not its value. The generated application obtains actual
annotations/defaults by inspecting the imported callable. Selection uses exact
comma-separated names; ignore wins over selection. An empty selection string
means all discovered functions, not none.

### Runtime behavior

Generated POST routes call synchronous functions or await asynchronous functions.
Zero-argument calls work. Invalid/missing typed parameters, malformed nested
structures and extra public fields on parameterized routes receive 422 responses.
Pydantic may coerce scalar values; this is not strict Python instance checking.
A bounded 1,000-element nested request is exercised without wall-clock assertions.

Underscore-prefixed names and names such as `model_dump`, `model_config`,
`__root__` and `field_1` work as public parameter aliases. Internal generated field
names are not an alternative public input vocabulary (a regression fixed here).
Ordinary user-function exceptions return 500 with `Function execution failed`;
exception details remain in server logs. Explicit FastAPI `HTTPException` status
and detail are intentionally passed through as application responses.

### Source, notebooks and execution boundary

Analysis, transformation and generation do not import supplied modules, evaluate
annotations, run decorators or execute notebook cells. Hostile fixtures attempt
file creation, environment mutation, network connection and an exception. None
runs during generation; each is separately observed at trusted runtime import.
Network attempts at that boundary are intercepted by tests, never sent.

NotebookTransformr uses **nbconvert PythonExporter**, including its IPython
source transformation. Apizr parses the exported Python, rejects AST calls to
`get_ipython`, strips exporter shebang/encoding/execution-count comment lines,
and formats the script with the runtime Black API. It does not run a notebook
kernel or replay stored outputs. Ordinary cell metadata, prior outputs and
execution counts do not change generated files. Markdown is exported as comments;
changes to source Markdown can therefore change artifact bytes. Multiple complete
code cells and a parenthesized expression split across cells work. A bounded
90,000-character comment cell is tested. Text and binary streams remain accepted
by the transformer.

### Import inference and files

Static `import package`, `import package.submodule`, aliases, and absolute
`from package[.submodule] import object` map to the root import name. Distribution
metadata and known aliases (for example PIL → Pillow and yaml → PyYAML) are used
offline; absent metadata falls back to replacing underscores with hyphens.
Installed versions are pinned only when target and host Python versions match.
Explicit requirements remain the escape hatch for reliable dependency control.

Local Python files and ordinary packages are copied without execution; circular
local imports terminate through the visited-name set. Relative imports inside
copied ordinary packages work. A module symlink whose resolved target stays in
the source tree is copied as a regular file. Directory/package symlinks and any
nested package symlink are rejected. Output containment and existing-file
preservation are exercised at both pipeline and standalone-writer boundaries.

Identical explicit source, configuration and dependency environment produce
identical generated file contents across output directories, including adversarial
Unicode, async and notebook cases. Artifact bytes do not gain timestamps, random
identifiers or output-directory paths. Input source can itself contain an absolute
path and is preserved; the manifest deliberately reports the requested output
location and is not part of the content-equality assertion. Apizr artifacts must
be independently hashable and attestable without an attestation dependency.

## EXPLICITLY REJECTED

- `*args`, `**kwargs` and their combinations: no fixed JSON schema can be inferred.
- Empty callable selections for API generation, including Markdown-only notebooks,
  empty cells, lambda-only inputs and class-only inputs.
- Malformed Python and notebooks, non-object notebook JSON, and unsupported
  annotation binary operators. HTTP generation/analysis returns a client error,
  not an internal traceback. Primary malformed input produces no generated files.
- IPython line/cell magics and shell syntax transformed into `get_ipython` calls.
  This is a static conversion limitation, not a runtime security sandbox.
- Unsupported Python targets, source/output equality, non-empty pipeline output,
  invalid generated module filenames, traversal (POSIX/Windows), symlink escapes,
  generated API filename collisions and output inside a package being copied.
- Ambiguous import-to-distribution mappings: supply explicit requirements.
- Oversized uploads: the existing 10 MiB boundary remains covered.
- Existing output files, including dangling symlinks, in active and standalone
  writers. Repeated generation requires a fresh directory or explicit user cleanup.

CPython rejects 250 nested parentheses predictably with `SyntaxError`; a bounded
80-parenthesis expression, 35 nested generics/blocks, 300 arguments/functions and
300 Literal values are exercised. These are observations of bounded cases, not
a comprehensive resource quota. Extremely deep or huge valid ASTs can still hit
interpreter recursion/memory limits. No wall-clock performance guarantee or
runtime sandbox is claimed.

## LEGACY OBSERVED — design decisions required

| Behavior | Observation | Decision before metadata migration |
| --- | --- | --- |
| Duplicate names | Two metadata records and POST routes; both inspect/call the final Python binding. Dispatch takes the first route while OpenAPI describes the last operation. Earlier defaults with renamed later arguments can cause import-time `KeyError`. | Reject duplicates, model final bindings, or represent overloads explicitly; tracked in [#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28). |
| `typing.overload` | Stubs are discovered separately; final implementation annotations control runtime validation. | Define overload-set discovery and schema policy. |
| Definitions inside module blocks | An `if False` function is discovered despite being absent at runtime; runtime import can fail. | Define lexical scope versus runtime reachability. Do not execute input to decide. |
| Decorators | Syntax is omitted from metadata. `functools.wraps` can preserve runtime signature/hints; a replacement wrapper without it can lose validation or break defaults. Decorator factories execute only at trusted import. | Define explicit decorator handling; no Apizr decorator API yet. |
| Generators | Sync generators serialize to arrays; async generators are incorrectly awaited and return sanitized 500. No generator flag exists. | Reject or define streaming/collection behavior explicitly. |
| Closures | Only the outer callable is exposed; a returned function currently serializes as `{}`. | Define allowable response types. |
| Return annotations | Recorded but no generated response schema/validation; a function annotated `-> int` can return a string. | Decide response validation and schema contracts. |
| Default `None` with `int` | Missing body uses the default and returns null; explicit null is rejected as invalid int. | Decide default validation independently of nullable typing. |
| Zero-argument input | Unexpected JSON body is ignored because no request model exists. | Decide whether zero-argument routes should forbid a body. |
| `/health` name | Built-in GET health and user POST health coexist. Only user POST appears in OpenAPI. | Decide reserved endpoint names/methods before changing routing. |
| Annotation representation | Literal values, quoted forward-reference names and nested union details can be lost. Runtime may still resolve the original source correctly. | Model syntax and resolved types separately; do not treat current metadata as a complete type schema. |
| Callable annotations | Runtime import succeeds, JSON callable values fail validation, and OpenAPI returns 200 with a dangling request-schema reference. | Explicitly reject non-JSON input contracts or define an adapter. |
| Arbitrary classes/unresolved names | Analysis and generation can succeed, then Pydantic schema construction or `get_type_hints` fails at import. | Decide generation-time diagnostics that do not evaluate user code. |
| Dependency scope | Requirements inference scans function/class bodies, TYPE_CHECKING, conditional and dead-code imports. AST import metadata skips function/class bodies. | Separate lexical dependencies from runtime requirements; preserve uncertainty. |
| Dynamic/relative/namespace imports | Dynamic import strings and root relative imports are not inferred/copied. Namespace packages without `__init__.py` are not bundled and may be guessed as external distributions. | Require explicit dependencies or introduce bounded resolution rules. |
| File/package collision | Copying prefers `shared.py` over a sibling `shared/__init__.py`; normal Python lookup can prefer the package. | Reject ambiguous source trees or define resolution order. |
| Stdlib shadowing | A local `json.py` is copied but not declared external. Runtime effects depend on import-cache state. | Define reserved/shadowed module policy. |
| Split function body across notebook cells | IPython dedents each cell; a function header in one cell and indented body in another produces `IndentationError`. Parenthesized expressions can span cells. | Define supported notebook cell composition instead of promising arbitrary concatenation. |
| Partial output after later-stage failures | Copy/dependency/schema failures can leave incomplete local artifacts; CLI fails and HTTP returns no ZIP. Generation is not transactional. | Decide atomic publication/cleanup without erasing user files. |

These observations are asserted as such, not silently fixed or promoted to
SUPPORTED. File/package collisions and dynamic imports are not solved by the
static dependency inferencer.

## FUTURE CANDIDATE

Class, classmethod, staticmethod, instance-method and abstract-method capabilities
remain unimplemented because class bodies are intentionally not traversed.
Lambda exposure, explicit closure/stream contracts, reliable dynamic dependency
resolution, decorator-driven configuration and notebook cell composition need
separate design work. The existing engine/plugin architecture is not extended.

Historical issue review (all remain open):

- [#1 — Notebook Conversion](https://github.com/Alien6-Studio/outerspace-apizr/issues/1):
  the single-command ordinary-notebook workflow exists and is smoke-tested.
  Preserving *all* dependencies/configuration is not guaranteed for dynamic
  imports, namespace packages, magics or arbitrary notebook state; acceptance
  criteria are broader than current support.
- [#5 — classes/classmethod](https://github.com/Alien6-Studio/outerspace-apizr/issues/5):
  explicitly deferred, protected against accidental method exposure.
- [#15 — plugin system](https://github.com/Alien6-Studio/outerspace-apizr/issues/15):
  no plugin API exists or is implemented here. Extension boundaries need future
  architecture work; the current characterization does not establish that this
  proposal is already fulfilled or definitively superseded.
- [#16 — notebook decorators](https://github.com/Alien6-Studio/outerspace-apizr/issues/16):
  ordinary Python decorator syntax survives but does not configure Apizr.
  Decorator-based product behavior is deferred, not implied by discovery success.

## Small safety/correctness fixes made after reproducing failures

1. Non-object JSON notebooks (`[]`, `null`) produced internal AttributeErrors/500;
   validate their outer object shape before nbconvert, yielding actionable 400.
2. Unsupported annotation operators raised a custom TypeError past HTTP/CLI
   handlers; catch the specific `AnnotationException`, without hiding arbitrary
   TypeErrors or catching BaseException.
3. `populate_by_name=True` accepted generated internal field names absent from
   the public schema. Remove it; public aliases and reserved-looking user names
   continue working. Routing and response generation are unchanged.
4. Output placed inside an imported package reached self-recursive `copytree`.
   Reject the overlap before copying. The reproducer replaces copytree with a
   sentinel, so the test never allocates a recursive filesystem tree.
5. Context, notebook, requirements, Docker and standalone result writers could
   overwrite existing files. Use exclusive creation; multi-file Docker/Gunicorn
   operations also preflight existing destinations before writing any output.
6. Standalone FastAPI/Gunicorn configured filenames could escape the declared
   directory. Apply POSIX/Windows filename validation; reject colliding Gunicorn
   output names. No filename-based escape or overwrite is retained as legacy
   behavior merely to keep a characterization test green.

The direct standalone writers now deliberately reject overwrite attempts; this
is a small compatibility change for callers that previously relied on overwrites.
Filesystems are assumed not to be concurrently modified by an adversary; these
checks are not a general race-resistant filesystem sandbox. Existing historical
fixtures, pipeline design, GPL terms and Python support range remain unchanged.

## Property tests and mutation resistance

Six Hypothesis properties exercise valid signatures/discovery order, selection
and ignored scopes, repeatability/state reset/purity, malformed-source handling,
request schema/signature consistency, and deterministic artifact contents.
Strategies generate bounded valid grammars and selected malformed variants;
there are no broad assumptions or disabled health checks. Each example gets its
own temporary state. Standard Hypothesis failure persistence/shrinking remains
enabled in `.hypothesis/` (ignored by Git), and `print_blob=True` emits replay
information. Deadlines are disabled to avoid machine-speed assertions; example
counts are bounded (15–60 per property). See the
[Hypothesis replay documentation](https://hypothesis.readthedocs.io/en/latest/tutorial/replaying-failures.html).

The tests fail if nested/class bodies start exposing callables, ignore stops
winning, variadics are accepted, generation executes source, containment is
inverted, or a parameterized route starts accepting unexpected public fields.
Both permitted and rejected paths are tested. No heavyweight mutation system is
added. A green test count alone does not demonstrate completeness.

## Annotation compatibility matrix

Every row is exercised with and without `from __future__ import annotations`.
Static column shows the root representation only; the lossiness tests cover
quoted names, Literal values, union children and tuple-shape differences.

| Source annotation | AST root | Generated runtime |
| --- | --- | --- |
| `int` | `int` | valid JSON accepted; invalid JSON rejected |
| `str` | `str` | valid JSON accepted; invalid JSON rejected |
| `float` | `float` | valid JSON accepted; invalid JSON rejected |
| `bool` | `bool` | valid JSON accepted; invalid JSON rejected |
| `bytes` | `bytes` | valid JSON accepted; invalid JSON rejected |
| `None` | `None` | valid JSON accepted; invalid JSON rejected |
| `list[int]` | `list` | valid JSON accepted; invalid JSON rejected |
| `dict[str, int]` | `dict` | valid JSON accepted; invalid JSON rejected |
| `tuple[int, str]` | `tuple` | valid JSON accepted; invalid JSON rejected |
| `set[str]` | `set` | valid JSON accepted; invalid JSON rejected |
| `typing.List[int]` | `typing.List` | valid JSON accepted; invalid JSON rejected |
| `typing.Dict[str, int]` | `typing.Dict` | valid JSON accepted; invalid JSON rejected |
| `typing.Tuple[int, str]` | `typing.Tuple` | valid JSON accepted; invalid JSON rejected |
| `Optional[int]` | `Optional` | valid JSON accepted; invalid JSON rejected |
| `Union[int, str]` | `Union` | valid JSON accepted; invalid JSON rejected |
| `int \| str` | `Union` | valid JSON accepted; invalid JSON rejected |
| `int \| None` | `Union` | valid JSON accepted; invalid JSON rejected |
| `Literal["a", "b"]` | `Literal` | valid JSON accepted; invalid JSON rejected |
| `Annotated[int, ...]` | `Annotated` | valid JSON accepted; invalid JSON rejected |
| `Annotated[int, Field(gt=0)]` | `Annotated` | valid JSON accepted; invalid JSON rejected |
| `Sequence[int]` | `Sequence` | valid JSON accepted; invalid JSON rejected |
| `Mapping[str, int]` | `Mapping` | valid JSON accepted; invalid JSON rejected |
| `Callable` | `Callable` | dangling schema reference |
| `Callable[[int], str]` | `Callable` | dangling schema reference |
| `Plain` | `Plain` | import error |
| `Item` | `Item` | valid JSON accepted; invalid JSON rejected |
| `Record` | `Record` | valid JSON accepted; invalid JSON rejected |
| `Choice` | `Choice` | valid JSON accepted; invalid JSON rejected |
| `"Item"` | `str` | valid JSON accepted; invalid JSON rejected |
| `Alias` | `Alias` | valid JSON accepted; invalid JSON rejected |
| `Node` | `Node` | valid JSON accepted; invalid JSON rejected |
| `"Missing"` | `str` | unresolved reference |

## Verification record

The updated suite passes **246 tests on each Python 3.11–3.14 runtime**, including
six Hypothesis properties (multiple examples per property, not counted as separate
pytest tests). The annotation matrix accounts for 64 eager/future-annotation cases;
counts are a consequence of the matrix, not an acceptance target. No pre-existing
test or historical golden fixture was removed.

Coverage is **65.95% on Python 3.14**, up from **56.07%** on the same runtime;
Python 3.11–3.13 report **66.16%**. The 55% floor remains unchanged. The audit
finds zero vulnerabilities in runtime (72 entries), development (30), documentation
(30) and security tooling (29); Hypothesis is development-only. Interactive prompts
and several legacy standalone paths remain less covered. These results neither
resolve the LEGACY OBSERVED decisions above nor establish unbounded input safety.

Core reproduction commands:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv build
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict
uv run --group security python scripts/audit_dependencies.py
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.11
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.14
uv run python scripts/smoke_container.py --python-version 3.11
uv run python scripts/smoke_container.py --python-version 3.14
```

Repeat the locked sync and full suite with separate environments for Python
3.11, 3.12, 3.13 and 3.14. The CI retains those four test/container targets and
both installed-wheel endpoints. Inspect completed PR checks for hosted CodeQL
results; no local pytest run is a substitute for CodeQL analysis.
