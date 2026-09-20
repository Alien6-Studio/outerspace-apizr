# Capability Graph v1

Capability Graph is a conservative static relationship layer over the
[Capability Catalog](repository-scanner-v1.md). It does not replace Inspection,
Capability IR or Readiness, and never executes repository code.

```text
Repository
    ↓ one bounded discovery of source bytes
Catalog v1 + retained in-memory source manifest
    ↓ static relationship analysis
Capability Graph v1
    ↓ FUTURE
Repository Readiness / Policy Analysis
```

## Boundary and versions

`apizr.graph.build_graph(catalog, sources, policy=GraphPolicy())` consumes a
validated Catalog and a mapping of relative source paths to exact bytes. Keys
must match **exactly the sources with successful Inspection**. Missing, extra,
colliding/uninspected entries and digest or byte-count mismatches are input
errors. The mapping is copied before validation. All successful sources are
SHA-256 checked against their Catalog source digest before graph parsing begins.
Catalog models are revalidated, including caller-supplied unchecked model copies.

`graph_repository(root, scan_policy=..., graph_policy=...)` returns a
`RepositoryGraph(catalog, graph)`. It discovers sources once using the existing
bounded, descriptor-relative, no-symlink scanner. Catalog and Graph consume the
same retained bytes; the graph does not reopen the repository. Bytes are never
added to Catalog JSON. Filesystem support remains Linux/macOS POSIX; the in-memory
API does not require filesystem access.

The contracts are independent:

- `apizr.graph-policy/v1`: resource policy and its canonical digest.
- `apizr.graph/v1`: relationship semantics and graph artifact.
- Existing `apizr.scan/v1`, `apizr.catalog/v1`, Inspection, IR and Readiness
  contracts are unchanged. Breaking graph semantics require a new graph version.

The package imports repository/inspection/core models and the standard library.
It has no dependency on transports, generators, Docker or execution backends.
Strict Pyright covers the package and CLI.

## Nodes and authoritative facts

| Kind | Identity | Metadata |
| --- | --- | --- |
| Module | `python-module:<logical-module>` | Relative source path, analysis availability |
| Capability | Existing `python:<module>:<name>` | Module, name, path, readiness, eligibility, execution form |
| External module | `python-external:<declared-module>` | Lexical module name only |

Every unique representable Catalog module becomes a module node, including
syntax-invalid modules with `analyzed=false`. Collision groups do not become
unique module nodes. Invalid/uninspected sources are not reparsed: Catalog
failure remains authoritative. Capability nodes index existing Catalog entries;
they do not duplicate IR or fabricate capabilities from arbitrary symbols.

`contains` is a Catalog membership fact with source declaration location and
syntactic availability. It asserts neither runtime availability nor eligibility.

External identities preserve dotted names, e.g. `requests.sessions`. They do not
assert that a module is standard-library, third-party, installed or missing.
There is no `find_spec`, environment lookup or dependency installation.

## Imports, references and calls

These are different facts:

1. A module imports another module.
2. A module or capability imports a capability symbol.
3. A capability refers to a symbol as a value.
4. A capability contains a direct call expression targeting a symbol.

An import is not proof of invocation. V1 records import declarations, conservatively resolved callable references and
direct calls. `return module.function` produces `references_capability`, never
`calls_capability`. Passing a callable as a value also records only a reference. There is no generic
`depends_on` relationship.

| Relationship | Meaning |
| --- | --- |
| `contains` | Direct Catalog module/capability membership |
| `imports_module` | Lexical import resolved to a unique repository module |
| `imports_external_module` | Lexical import with no matching repository module |
| `imports_capability` | Imported symbol resolved to a Catalog capability with stable binding |
| `references_capability` | Conservatively resolved loaded callable value in a capability body |
| `calls_capability` | Conservatively resolved direct `ast.Call` in a capability body |

A `calls_capability` edge means:

> A direct `ast.Call` expression in capability source has a target that Graph v1
> can resolve unambiguously to another Catalog capability under its conservative
> lexical binding rules.

It does **not** mean the branch executes, the call succeeds, runtime monkeypatching
cannot alter it, or dynamic dispatch is impossible.

Relationships retain one record per source occurrence: source/target IDs, kind,
relative path, start/end line and UTF-8 byte columns, availability and evidence.
Two calls on the same line remain distinct through their columns. Repeated
identical derived facts at the same occurrence are deduplicated; declaration
records preserve the full ordered alias list. Query helpers return unique sorted
target IDs rather than repeating occurrences.

A reference is a loaded `ast.Name` or complete `ast.Attribute` expression with a
stable Catalog capability target under the same binding rules as calls. Callee
expressions are represented by call relationships only; attribute prefixes are
not separate references. `alias = calculate` can record the reference to
`calculate`, but a subsequent `alias()` is not resolved through assignment flow.
Reference uncertainty uses its own diagnostic. This does not add points-to analysis.

## Lexical import inventory and resolution

Each declaration preserves `import` versus `from`, the declared module (including
an absent module in `from . import ...`), relative level, ordered imported names
and aliases, source span, owner and lexical scope. Resolution per imported name
is `module`, `capability`, `external`, `unresolved`, `ambiguous` or `star`.
Ordinary non-capability imports retain an unresolved symbol fact without noisy
warnings. A local base module import remains a separate edge even when an
imported capability or submodule is also resolved.

Absolute imports match exact unique logical module identities in Catalog.
Colliding names never fall back to external nodes. Relative imports resolve
against the current logical package: the current module for `__init__.py`, its
parent for ordinary modules. Level one stays in that package; each additional
level ascends once. An ascent beyond the package ancestry is a diagnostic, with
no guessed external filesystem location.

`from X import Y` can denote `X.Y` or an exported symbol of `X`. A unique
submodule resolves only without competing export evidence. A matching Catalog
capability resolves only with Readiness's **binding dimension READY**. A
submodule plus an exported capability/other binding is ambiguous. A direct
import of that same submodule is not a competing export (including package
`from . import sibling`); re-export chains and assignment aliases are not chased.
If no local interpretation exists, external or unresolved lexical evidence is
retained. A non-capability constant does not become a capability node.

## Calls and bindings

Supported forms include same-module `f()`, imported `f()`/`alias()`, module alias
`pricing.calculate()` and the longest established dotted import prefix in
`project.pricing.calculate()`. Same-module definition order does not prevent
resolution: function globals are looked up at invocation time. Different modules
may contain identically named capabilities; lookup always includes module identity.

Module bindings are inventoried from imports, definitions, assignments, valued
annotations, deletes, loop/with/exception targets, match captures and named
expressions. Repeated, conditional or rebound aliases are not stable call targets.
Multiple distinct unaliased dotted imports may establish one package root.
An annotation without a value does not itself rebind a module variable.

Capability-local scope is inventoried before any call resolution. Parameters,
assignments (including valueless annotations), imports, deletes, loop/with/except
and match targets, nested declarations and named expressions shadow globals
throughout the body. Generic type parameters also shadow module names. Lazy
PEP 695 type-alias expression subtrees are excluded from the containing scope.
A single unconditional local import can resolve later calls;
use before that import remains uncertain. Explicit `global` without a write may
use a module binding; global writes and `nonlocal` names are not resolved.
Comprehension targets shadow names only within their expression; named expressions
bind the containing scope.

Nested function/async function, class and lambda subtrees are excluded, including
their declaration expressions. Their calls/imports are not attributed to an outer
capability. Ordinary control flow and comprehensions in the capability are
included, with conservative conditional availability. V1 does not evaluate
branches: all children of a control-flow/boolean/comprehension construct are
marked conditional, including initial tests/iterables.

Caller readiness does not gate observed relationships. Target binding stability
comes from existing Readiness; the graph does not rerun that policy. Target
execution/input readiness may be unsupported while the binding itself is stable.
Graph resolution does not establish interface eligibility.

Calls through arbitrary objects, parameters, assigned aliases, closures,
collections, `getattr`, returned callables and decorators are not resolved. There
is no points-to analysis, runtime tracing or monkeypatch analysis.

## Star and dynamic imports

Star imports preserve the module import and a warning, without symbol expansion.
An unknown star binding conservatively prevents global/local name resolution in
that scope. Common unshadowed `__import__`, imported `importlib.import_module`,
and its direct imported aliases produce dynamic-import uncertainty at call sites.
Arguments are never evaluated, even constant strings. A shadowed or ambiguous
binding does not establish that the function is an import primitive. Merely
importing `import_module` is not proof it is called.

## Evidence and diagnostics

Syntax existence is `observed`. Resolved import/call target identity is `inferred`
from lexical syntax and Catalog facts, including aliases and relative resolution.
Unresolved/ambiguous symbol resolution has `unknown` evidence. Containment
resolution is `observed` Catalog membership. No numeric confidence is used.

| Code | Meaning | Behavior |
| --- | --- | --- |
| `APIZR-GRAPH-001` | Invalid source/Catalog linkage or inconsistent declaration | Input exception; no graph |
| `APIZR-GRAPH-002` | Ambiguous/unstable local import interpretation | Blocking diagnostic |
| `APIZR-GRAPH-003` | Invalid relative import ancestry | Blocking diagnostic |
| `APIZR-GRAPH-004` | Star import bindings unresolved | Warning |
| `APIZR-GRAPH-005` | Dynamic import unresolved | Warning |
| `APIZR-GRAPH-006` | Conditional/rebound import alias | Warning; no trusted call through alias |
| `APIZR-GRAPH-007` | Unstable capability call target/use before local import | Warning; no resolved call |
| `APIZR-GRAPH-008` | Aggregate graph/parser limit | Blocking, incomplete result |
| `APIZR-GRAPH-009` | Catalog module collision | Blocking; no unique module node |
| `APIZR-GRAPH-010` | Catalog Inspection unavailable | Blocking; skip source analysis |
| `APIZR-GRAPH-011` | Unstable callable reference | Warning; no resolved reference |

Codes and structured fields are semantics; messages/severity are presentation
properties. The graph also binds Catalog's exit status. `complete` means no
blocking Catalog/Graph diagnostic, **not** complete knowledge of runtime behavior.
External imports and ordinary unresolved library/object calls are normal.

## Bounds and failure behavior

| Policy field | Default | Maximum accepted |
| --- | --- | --- |
| `max_ast_nodes` | 500,000 | 2,000,000 |
| `max_relationships` | 50,000 | 200,000 |
| `max_calls` | 50,000 | 200,000 |
| `max_imports` | 10,000 | 100,000 |

All limits are aggregate across graphable sources. Every AST node, call and
import counts, including excluded nested scopes. Trees are counted before scope
indexes are retained. Traversal is iterative, with the existing scan byte/file
limits bounding parser input. Interpreter parser recursion exhaustion produces
an incomplete graph. AST resource accounting follows the host supported parser;
new syntax unavailable on an older interpreter remains subject to Catalog's
existing parse policy.

Any graph limit discards **all relationships, import declarations and external
nodes**, retaining Catalog module/capability identities and blocking diagnostics.
Module `analyzed` flags are false in this incomplete result. An arbitrary partial
prefix is never presented as a complete graph. Readiness/Inspection failures from
Catalog remain intact and are not independently reparsed or repaired.

## Canonical artifacts and queries

Canonical UTF-8 JSON uses sorted keys, compact separators, explicit defaults,
finite values and one trailing LF. Nodes sort lexicographically by ID;
relationships by `(source, kind, target, path, line, column, end_line, end_column)`;
imports by owner/path/line/column; diagnostics by path/location/code/limit.
Cycles and self-recursion are valid and require no graph traversal to serialize.

`graph_bytes` revalidates the typed document. `graph_digest` is the SHA-256 of
canonical bytes, separate from scan policy, repository, Catalog and graph policy
digests. There is no self-digest field, timestamp, host path, Git metadata or
random identifier. Body/comment changes bind new source/Catalog/graph digests;
unchanged topology may keep node IDs and endpoints. These are content bindings,
not cryptographic provenance or claims of authenticity.

Pure query helpers:

```python
from apizr.graph import graph_repository
from apizr.repository import ScanPolicy

result = graph_repository(".", scan_policy=ScanPolicy(source_roots=("src",)))
graph = result.graph
graph.module_dependencies("shop.checkout")
graph.capability_calls("python:shop.checkout:place_order")
graph.callers_of("python:shop.pricing:calculate")
```

Module dependencies here are direct module-scope local/external import edges.
Derived statistics count nodes, each relationship kind, declarations and
diagnostics; they stay outside the canonical document.

Committed schemas are [Graph v1](../specs/apizr-graph-v1.schema.json) and
[Graph policy v1](../specs/apizr-graph-policy-v1.schema.json). Tests compare fresh
model schemas and the reviewed five-module `tests/fixtures/graph/v1` golden.
Property tests cover relocation, input/enumeration order, aliases, topology,
shadowing, collision and cycles. Real audit hooks reject source execution,
repository writes, network, subprocesses and unwanted framework imports.

## Deliberately deferred

No effects/permissions/readiness propagation, transitive stored edges, repository
or agent scores, ranking, graph database, repository execution/generation,
class/method capabilities, visualization UI or attestation integration.
Repository-level governance/readiness questions remain tracked by issue #55.
Graph artifacts can be independently hashed without an attestation implementation.
