# Static capability readiness v1

Capability IR records source declarations. Readiness applies a separate, bounded
policy to those declarations and matching static source evidence. Neither model
executes source, imports user modules, resolves a repository or guarantees runtime
success. The [REST v1 consumer](rest-generator-v1.md) defines how eligible contracts
are exposed; readiness itself remains independent of that target.

```text
source → Capability IR v1 → readiness policy → readiness report
                                                |
                                  REST v1 / future consumers
```

## Version and compatibility

The policy identifier is `apizr.readiness/v1`, independent of
`apizr.capability/v1`. Readiness does not add fields to the IR or change its
canonical serialization, JSON Schema, golden fixture or document digests. Tests
pin their baseline hashes at `b82e5bf969ce27194075eb053412485941e7d0ce`.
Changes to readiness decisions require an explicit policy-version review.

The typed report references the exact IR document digest and source record. Each
assessment refers to a logical `python:<module>:<symbol>` identity and source span.
Symbols rejected by IR diagnostics still receive an assessment with `in_ir=false`;
they never become executable IR capabilities merely to appear in a report.

## States, dimensions and eligibility

- **ready:** enough static contract evidence for the policy's ordinary JSON/value
  interface. It does not prove successful import, invocation or serialization.
- **conditional:** a representable declaration has unresolved binding, dependency,
  initialization or input semantics.
- **unsupported:** this policy lacks an adapter for the declaration.
- **ambiguous:** no single coherent callable contract can be selected.

Binding, execution, inputs and outputs each contain ordered reasons and a derived
state. The overall state uses precedence ambiguous > unsupported > conditional >
ready. `can_generate_interface` is true only for an actual IR capability whose
overall state is ready. It means an adapter can be described without inventing
input semantics, not that execution is safe or that an adapter will execute successfully.

Unknown response schemas and absent runtime return enforcement are explicit
output limitations, not blocking states. All effects are preserved from IR and
remain unknown; they do not make every function ineligible. Future execution
policy must decide whether those unknown effects are acceptable.

## Binding and initialization policy

Module-level binding events are collected in lexical order without entering
function/lambda bodies or treating class members as module names. Function
binding occurs after its declaration-time expressions. Assignments, valued
annotated assignments, augmented assignments, deletion, later function/class
names, import aliases, loop/with/except targets, match captures and visible named
expressions are considered. Annotation-only statements do not assign a value.
Comprehension iteration targets do not escape their scope; visible named
expressions are conservatively retained. Later events matching a function name
produce conditional binding. Branches/loops are not evaluated: even a possible
rebinding in dead-looking code is reported.

Conditional IR definitions and all ordinary decorators remain conditional. No
runtime decorator whitelist exists. Recognized overload declarations belong to
the IR analyzer and are not ordinary implementation decorators. IR duplicate and
overload errors become ambiguous assessments, preserving the original diagnostics.

The initialization heuristic deliberately permits pass, docstring/constant
expressions, ordinary imports, literal-only assignments and undecorated function
declarations whose defaults are literal-only and annotations contain no calls. Literal-only here means
constants, list/tuple/set/dict displays and unary +/- applied recursively to
literal-only expressions, without unpacking. This is a bounded syntactic allowance,
not proof that Python evaluation or memory allocation succeeds.

Other top-level statements produce initialization uncertainty: calls, explicit
raise, nonliteral assignments, control-flow blocks and class construction. These
are considered both before and after a definition, because later failure can also
prevent module import from completing. Overload stubs already associated by IR
are excluded from this heuristic. Definition-time calls/decorators remain visible;
function bodies are not treated as module initialization.

Visible `globals`/`locals`/`vars` access, `exec`/`eval` or star imports make namespace
binding uncertain. Dynamic imports (`__import__`, `import_module`, including
visible imported aliases/attribute calls) create dependency uncertainty. Static
relative or non-stdlib imports create unresolved local/namespace/external dependency
reasons; no files or distributions are searched. Imports within a candidate's body
are inspected syntactically for dependency uncertainty, including nested scopes,
without claiming a call graph. Ordinary stdlib imports are a bounded allowance,
not a promise that their initialization succeeds. The allowed roots are frozen in
`apizr.readiness.stdlib.STDLIB_ROOTS`, using the intersection of CPython 3.11–3.14
stdlib catalogs. The analyzer never consults the host's stdlib catalog. New,
removed or otherwise unlisted roots remain unresolved even if available on the
current interpreter; changing this allowance requires policy-version review.

## Input and output contracts

Known syntactic primitives `str`, `int`, `float`, `bool`, `None` and JSON-shaped
list/dict/tuple/set contracts are eligible when members are representable. A dict
requires string keys; tuples may be fixed-length or `tuple[T, ...]`. Unsubscripted
containers retain their declared shape with unconstrained members; absent
annotations are unconstrained JSON contracts. No stronger validation is inferred. Union, Optional and scalar Literal members (including signed finite numbers)
are classified recursively. Callable and bytes need adapters and are unsupported.
Annotated retains its metadata but is conditional: v1 does not invent or discard
constraint semantics. Unknown expressions, arbitrary classes, aliases and forward
references are conditional, even when a class declaration exists locally.

Builtin/typing spellings are syntax conventions, not imported runtime objects.
Visible bindings that replace those spellings, or attribute/subscript writes through
their roots, are conditional. Direct typing
imports can be recognized when uniquely bound and their symbol is not renamed.
Renamed symbol imports remain conditional because IR v1 does not preserve their
resolution for consumers (the boundary inconsistency tracked in issue #39). Module
aliases such as `t.List` retain the explicit type member and remain recognizable.
Arbitrary alias expressions are never evaluated. Unbound conventional typing names may describe
an adapter contract, but do not establish runtime importability.

Implementation and recorded overload inputs are reviewed independently; no
overload dispatch or signature merging is inferred.
Defaults remain unevaluated IR expressions. Calls in definition-time expressions
add initialization uncertainty. Declared output types use the same structural
review for reporting; missing, unresolved and non-JSON returns are reported as an
unknown response schema and never alone block interface generation. Return
`enforcement` remains `none`. Sync/async functions may be eligible; generators and
async generators require a future streaming adapter and are unsupported here.

## Stable reason codes

| Code | Meaning | Dimension / impact |
| --- | --- | --- |
| APIZR-READY-001 | Conditional module definition | binding / conditional |
| APIZR-READY-002 | Decorator may replace binding | binding / conditional |
| APIZR-READY-003 | Later name binding or deletion | binding / conditional |
| APIZR-READY-004 | Module initialization may abort | execution / conditional |
| APIZR-READY-005 | Generator requires an adapter | execution / unsupported |
| APIZR-READY-006 | Async generator requires an adapter | execution / unsupported |
| APIZR-READY-007 | Unconstrained input, no stronger semantics known | inputs / ready, limitation |
| APIZR-READY-008 | Dynamic namespace binding unresolved | binding / conditional |
| APIZR-READY-009 | Duplicate callable symbol | binding / ambiguous |
| APIZR-READY-010 | Ambiguous overload association | binding / ambiguous |
| APIZR-READY-011 | Variadic input unsupported | inputs / unsupported |
| APIZR-READY-012 | Non-JSON input needs an adapter | inputs / unsupported |
| APIZR-READY-013 | Runtime input type unresolved | inputs / conditional |
| APIZR-READY-014 | Dynamic import dependency unresolved | execution / conditional |
| APIZR-READY-015 | Local/namespace/external dependency unresolved | execution / conditional |
| APIZR-READY-016 | Response schema unknown; no return enforcement | outputs / ready, limitation |
| APIZR-READY-017 | Annotation metadata semantics unresolved | inputs / conditional |
| APIZR-READY-018 | Callable construct has no IR function contract | execution / unsupported |

Reasons contain code, policy-inference evidence, source line and optional
parameter name. Messages are presentation, never identifiers. Reasons are
uniquely ordered by line, code and parameter; assessments by capability ID.

## Python API and deterministic artifacts

`assess(document, source)` in `apizr.readiness` accepts IR plus the exact Python
text/bytes that produced it. For notebooks, supply the transformed Python text;
its digest must match `source.transformed_digest`. It checks both the digest and
reanalyzed declaration/diagnostic equality before assessing the source. The
original notebook digest remains bound through the IR document digest.

`apizr.inspection.inspect_source(source, module_name=...)` and
`inspect_file(path, module_name=...)` assemble a typed inspection result. File
inspection supports one `.py` or `.ipynb`; logical identity is explicit in Python.
The notebook adapter reads original bytes once and retains the exported Python as
transient analysis evidence, never as an extra IR field.

Readiness canonical JSON uses sorted keys, compact separators, explicit defaults,
UTF-8 and one terminal LF. Its SHA-256 digest is external. An inspection envelope
contains `schema_version=apizr.inspection/v1`, `capability_ir`, `ir_digest`,
`readiness` and `readiness_digest`. Its deterministic JSON is a presentation
contract, not canonical IR bytes. No artifact contains its own digest. No paths,
timestamps, random identifiers or attestation-specific fields are added.

## Command line

```sh
apizr inspect pricing.py
apizr inspect pricing.py --format json
apizr inspect pricing.py --ir
apizr inspect notebook.ipynb --module-name project.pricing
```

Default text includes logical source identity, digests, capability states,
execution form, input/output limitations, unknown effects and reason codes.
`--format json` emits the inspection envelope. `--ir` emits only canonical IR
bytes; the two output selectors are mutually exclusive. No output files are
written implicitly. CLI identity defaults to the filename stem, normalized as a
Python module name; invalid names require an explicit `--module-name`. Different
paths with the same logical module and source produce identical machine bytes.

Exit codes are the same in every output mode:

- **0:** inspection completed, with ready and/or conditional assessments only;
- **1:** inspection completed, with unsupported/ambiguous assessments or IR errors;
- **2:** input, syntax, unsupported extension, read or notebook-conversion error.

Conditional is not an execution approval: it is nonblocking for inspection but
not eligible for adapter generation under this policy. Empty sources report zero
capabilities and exit 0. Ordinary user errors use stderr without a traceback.

A small CLI router recognizes `inspect` and delegates all historical arguments to
the unchanged generation CLI. `apizr --script ...` and `apizr --notebook ...` retain
their behavior; there is no mandatory `generate` subcommand.

## Limits

This is not Python abstract interpretation, import resolution, a resource
sandbox, full effect inference or a guarantee of runtime safety. Reflection,
indirect aliases and arbitrary mutation cannot be resolved completely. The
explicit bounded allowances and unknown effects remain visible to consumers.
The REST v1 generator consumes this report without redefining eligibility. Historical issue #28
remains open for the unchanged legacy pipeline; this policy addresses the
separate static-evidence problem in issue #31.
