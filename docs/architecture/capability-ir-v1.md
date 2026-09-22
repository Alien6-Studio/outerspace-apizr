# Capability IR v1 — normative specification

This specification defines the internal source-analysis contract, independently of
Apizr's package version. Its empirical input is the
[legacy behavior contract](legacy-behavior-contract.md), recorded at
`a386f507000852ab19e8239f6cbc8b4b3b8d249a` (246 tests, 65.95% branch-aware coverage).
Legacy ambiguities are evidence for this design, not compatibility requirements for
this new domain. The existing generation pipeline remains unchanged.

```text
                 Python / Notebook
                         |
            +------------+------------+
            |                         |
     Legacy pipeline          Capability Analyzer
            |                         |
     CodeAnalyzr JSON          Capability IR v1
            |                         |
      FastAPI / Docker            Consumers
                                  /   |   \
                               REST  MCP  Runtime
```

The original IR change introduced the right-hand analyzer and IR. Current
[repository and runtime consumers](overview.md) are separate layers. A capability is a
lexically observed module-level function contract, not a promise that importing,
binding, invoking or serializing it will succeed. Classes, nested functions,
repository resolution, generators consuming the IR, effect inference, runtime
execution, sandboxing, plugins, MCP, AI and attestation implementations are outside
v1's scope. Generator *definitions* are represented, but never invoked.

## Document, identity and source

The required schema identifier is `apizr.capability/v1`. A document contains one
source, capabilities and diagnostics. Models are frozen, typed, and reject unknown
fields and inconsistent identities. Collections are tuples. The canonicalizer
sorts capabilities by ID and diagnostics by source line, code and message;
signatures, decorators and overloads retain source order. Duplicate IDs are
invalid even when constructing a document directly.

IDs are `python:<module>:<qualified-symbol>`. Module names are explicit dotted
Python identifiers (NFKC normalized, no keywords); symbols are AST-normalized
identifiers. V1 admits module-level functions only, so qualified symbol equals
name. IDs never depend on files, paths, whitespace or comments. Inspection of a
file requires the caller to supply its logical module name; no filename inference
or project import resolution occurs.

Source kind is `python` or `notebook`. Source locations contain logical module,
symbol, one-based definition line and inclusive end line. No absolute paths,
output paths, timestamps, hostnames, random IDs or working directories are emitted.
Python source digest is SHA-256 of **exact original bytes**, including comments,
encoding declarations, BOMs and line endings. Byte input is decoded using Python's
PEP 263 encoding detection. String input means its UTF-8 encoding, without further
normalization. Invalid encoding, syntax or logical module names raise ordinary
input exceptions; they do not produce partial IR documents.

Notebook inspection reads original bytes once, hashes them, and uses the existing
non-executing NotebookTransformr exporter through a separate adapter outside the
core package. A second digest hashes the exact UTF-8 Python text returned by that
exporter, before formatting or analysis. Locations refer to that transformed text.
Exporter/dependency versions can change transformation output; the second digest
makes this observable. Non-code cells have no function contracts. Notebook magics
remain rejected by the characterized adapter. No kernel is started.

## Function and signature contracts

A capability includes ID, name, qualified name, kind `function`, source span,
optional docstring, execution form, signature, decorators, overload contracts,
availability, effects and evidence. Missing docstrings remain JSON null; no prose
is generated. Docstrings use Python AST's cleaned docstring convention.

Execution forms are `sync`, `async`, `generator`, `async_generator`. Yield detection
is confined to the function's own scope (not nested functions, lambdas or classes).
This is a syntactic observation, never a transport or runtime support guarantee.

Parameters retain Python binding order, name, kind (`positional_only`,
`positional_or_keyword`, `keyword_only`), required flag, optional declared type and
optional default expression. Null default-expression means *no default*; the
string `None` is a present default. Required must agree with default presence.
Defaults are normalized AST expressions and are never evaluated. Annotation and
default are independent: `x: int = None` differs from `x: int | None = None`.
Variadic implementations and variadic overload contracts are rejected with an
error rather than truncated to fixed signatures. Return annotation is separate,
and enforcement is always `none`; neither this analyzer nor the legacy runtime
adds enforcement based on this representation.

Every annotation retains `declared`: `ast.unparse` of its parsed expression.
Normalization discards lexical whitespace, comments, redundant parentheses and
quote style, while preserving literal values, actual forward-reference names,
operands, nested members and metadata expressions. No name resolution or alias
evaluation occurs. Forms classify syntax only: `name`, `attribute`, `subscript`,
`union`, `forward_reference`, `literal`, or `unknown`. `Optional`, `Literal`,
`Annotated`, `Callable`, collection types and arbitrary libraries' generics all
retain their complete subscript expression. A syntactic `union` is not proof that
an overloaded `__or__` implements typing semantics. Unsupported structural forms
remain `unknown` with the complete declaration and an informational diagnostic.
The v1 canonical expression contract is pinned by the golden and cross-version
tests for supported Python syntax; new Python syntax is parsed by the running
interpreter and is not promised to parse on older interpreters.

## Evidence, effects and availability

`Evidence` is reusable: `declared`, `observed`, `inferred`, `unknown`. Names,
locations and execution syntax are observed. Annotations/defaults/decorators are
declared. Future static heuristics must be inferred, not promoted to declared or
observed runtime facts. V1 has no AI-origin category.

Effects have explicit tri-state values `true`, `false`, `unknown` and evidence.
Filesystem read/write, network, environment, subprocess, state mutation, secrets
and external service access are all `unknown` with unknown evidence. **Unknown is
not false.** The analyzer performs no effect inference, even for an empty body.
The typed effect record is an extension point for future optional categories.

Availability is `unconditional` (observed direct module statement) or `unknown`.
Any control-flow scope (`if`, loops, `try`, `with`, `match`, etc.) makes it unknown
and produces a warning, even `if True` or `if False`: no reachability evaluation.
An ordinary decorator also makes availability unknown because it can replace the
binding; its complete expression is preserved without interpreting semantics.
An unconditional definition is still not a runtime guarantee: earlier top-level
exceptions, imports, subsequent rebinding, dynamic namespace operations or a
failing default can prevent or replace the binding. Binding/dataflow resolution is
explicitly deferred. All contracts are observations, not runnable entry points.

## Duplicates, overloads and diagnostics

Two or more concrete definitions of one symbol are ambiguous: emit ERROR 001 and
omit that symbol's capability. Do not select the first or last definition.

Recognize `typing.overload` and imported aliases only when a direct, preceding
module-level import uniquely binds the decorator root throughout module scope.
Recognize bare `overload` without such evidence as ambiguous, not as executable.
Rebindings/conditional imports make a matching overload marker ambiguous. Accept
an overload group only when all its declarations and its single implementation
are unconditional consecutive module statements, declarations precede the
implementation, their sync/async nature agrees, and the marker is the only stub
decorator. Preserve those signatures as declared contracts in source order. No
overload dispatch or signature compatibility solving is implemented. Stub-only,
conditional, reordered, interleaved or multiply decorated groups produce ERROR
004 and no capability. Unsupported variadics produce ERROR 002 and no capability.
Duplicate concrete implementations still produce ERROR 001 independently.

Diagnostics use stable enums for code and severity (`info`, `warning`, `error`),
a message and logical source span. They do not embed paths or source snippets.

| Code | Meaning | Severity |
| --- | --- | --- |
| APIZR-CAP-001 | Duplicate concrete symbol | error |
| APIZR-CAP-002 | Variadic signature unsupported | error |
| APIZR-CAP-003 | Control-flow definition availability uncertain | warning |
| APIZR-CAP-004 | Overload association ambiguous | error |
| APIZR-CAP-005 | Decorator binding uncertain or lambda assignment unsupported | warning |
| APIZR-CAP-006 | Type structure unknown; declaration retained | info |

Methods and nested scopes are intentionally skipped without per-member noise.
Historical issues about those features remain open. Lambda assignments are not
function-definition contracts and receive 005 when directly assigned to a name.

## Canonical bytes and digests

`canonical_bytes(document)` serializes the validated model in JSON mode, including
explicit nulls and defaults, with lexicographically sorted object keys, UTF-8
(`ensure_ascii=False`), compact separators `,` and `:`, no NaN, and exactly **one
terminal LF**. Collections follow the ordering above. No YAML representation is
canonical. Documents loaded from canonical JSON round-trip to identical bytes.

`document_digest(document)` returns a typed SHA-256 digest of those bytes, with
lowercase 64-character hex value. That digest is external, never embedded in its
own input. Source digests and document digests are separate concepts; formatting
changes can change both source digest and source locations without changing IDs.

**Capability IR is an attestable artifact, not an attestation format.**

Independent tools can hash or attest the artifact. There are no signatures,
receipts, SLSA fields or dependencies on an attestation product.

## API, version policy and limitations

```python
from apizr.capabilities import (
    canonical_bytes,
    document_digest,
    inspect_file,
    inspect_source,
)

ir = inspect_source(b"def calculate(x: int) -> int: return x\n", module_name="pricing")
artifact = canonical_bytes(ir)
digest = document_digest(ir)
# inspect_file(Path('pricing.py'), module_name='pricing') reads exact file bytes.
```

Notebook entry point: `apizr.capability_notebooks.inspect_notebook(path,
module_name=...)`. Core imports only stdlib and existing Pydantic; the notebook
adapter owns the optional exporter boundary. Inspection performs no user imports,
execution, network requests or subprocesses. File APIs read only the explicitly
supplied input. In-memory inspection does not access the filesystem. Static
inspection is not a resource sandbox: pathological input can exhaust parser
limits. Importing/running analyzed or generated code requires trusted input.

V1 readers must continue to understand v1 documents; meaning cannot silently
change. Breaking semantics require v2. Because v1 validation rejects extra fields,
additive optional fields require coordinated reader upgrades and a compatibility
review before emission; they are not automatically backward compatible. Package
releases do not rename the schema. The generated
[JSON Schema](../specs/apizr-capability-v1.schema.json) and single golden document
are tested against the models/serializer. Compatibility CI retains the global 90% branch-aware coverage floor and additionally requires
90% branch-aware coverage for `apizr.capabilities`.
The CLI exposes `inspect` and repository/interface/runtime commands as separate
consumers; none changes the IR v1 meaning.

Known limits include lexical binding/reachability, unsupported variadics and
classes, no type/alias/runtime resolution, conservative overload association, no
runtime argument/return enforcement, and syntax availability tied to the parser's
Python version. These are explicit boundaries rather than inferred safety claims.

Problem tracking: [#30](https://github.com/Alien6-Studio/outerspace-apizr/issues/30)
covers information loss for independent consumers;
[#31](https://github.com/Alien6-Studio/outerspace-apizr/issues/31) was addressed by the separate Readiness layer; lexical discovery alone still
does not establish callable availability. The historical duplicate
behavior in [#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28) remains
open for the legacy pipeline.
