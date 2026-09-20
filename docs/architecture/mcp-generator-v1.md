# MCP generator v1

MCP is a second consumer of Capability IR v1 and Readiness v1. It maps an eligible
capability to one Tool, using the same interface contract as REST. It does not
analyze Python declarations independently.

```text
source → Capability IR v1 → Readiness v1 → apizr.interfaces
                                            ├→ REST v1
                                            └→ MCP v1
```

## Protocol and SDK boundary

The target is [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28).
The generated runtime requires the [official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
`mcp>=2.2,<3`; the reviewed and locked development version is 2.2.0. This is the
stable v2 API, not the old FastMCP API. AnyIO and Uvicorn are explicit runtime
requirements because the adapter uses them directly. MCP is a development/test
dependency of Apizr, not a dependency needed to inspect or generate artifacts.

The adapter uses the SDK's public [`Server` API](https://py.sdk.modelcontextprotocol.io/advanced/low-level-server/).
It accepts precompiled schemas without deriving another contract from runtime
annotations. Unlike the high-level `MCPServer`, which registers resource/prompt
managers even when empty, this API advertises only the supplied Tool handlers.
No private SDK attributes, custom JSON-RPC implementation or vendored SDK code are
used. SDK negotiation, envelopes, transports and compatibility remain SDK concerns.

## Shared interface contract

`apizr.interfaces` owns:

- `TypeSpec`, input and invocation contracts;
- revalidation of Inspection, IR/readiness/source digests and identities;
- selection and consumption of `can_generate_interface`;
- lowering IR-declared types to JSON Schema;
- executable integrity, logical module loading and callable-shape verification;
- JSON value validation and Python argument reconstruction;
- canonical artifact serialization and exclusive output writing.

This package imports neither FastAPI nor MCP. The compiler never reads runtime
annotations or reruns readiness. It only lowers the declared type expressions
already stored in IR. IR and Readiness models, schema versions and digest rules
are unchanged by this extraction.

The REST package retains routes, HTTP responses and OpenAPI. The MCP package
retains Tool names, MCP metadata, results and transports. Runtime source code for
the shared core is copied into the standalone MCP bundle as `apizr_runtime.py`.
The generated server does not import Apizr.

## Eligibility

`assessment.can_generate_interface` is the sole eligibility authority. Generation
without selection refuses any non-eligible callable declaration; selection accepts
only eligible names or full capability IDs. Conditional, unsupported and ambiguous
capabilities cannot become Tools. Unknown or empty selections fail. No force,
unsafe or ignore-readiness option exists.

The shared inspection boundary verifies IR and readiness digests, exact source
bytes, executable digest (notebook export where applicable), logical identities,
assessment membership and evidence. Supplying mismatched artifacts fails before
output. Sync and async Python functions are supported; generators and async
generators remain unsupported by Readiness.

## Tool identity and descriptions

The original identity remains `python:<module>:<symbol>`.

For one source module, preserve a symbol as its Tool name when it matches
`[A-Za-z0-9_.-]{1,64}` and does not begin with the reserved `apizr_` prefix.
Otherwise use `apizr_` followed by the full lowercase SHA-256 of the UTF-8
capability ID. Reserving that prefix separates preserved and encoded names; any
remaining collision is rejected explicitly. Unicode and long Python names are
therefore deterministic without changing IR identity.

The manifest stores both names and the capability ID. Advertised Tools also carry
`_meta["sh.outerspace.apizr/capability-id"]`. Descriptions are exact IR docstrings.
Absent docstrings produce no description; no inferred or generated prose is added.

## Input schemas and invocation

`mcp-tools.json` statically records the advertised Tools and their `inputSchema`.
These schemas are exactly the same object schemas used inside REST request bodies.
They use JSON Schema 2020-12, the protocol default dialect.

| Input | Shared interpretation |
| --- | --- |
| int, float, str, bool, None | JSON integer, finite number, string, boolean, null |
| Any / unannotated | Unconstrained finite JSON |
| list | Array; members validated |
| dict with string keys | Object; values validated |
| fixed / variadic tuple | Fixed positional / homogeneous array, reconstructed as tuple |
| set | Unique array, reconstructed as set; members must be hashable |
| Union / PEP 604 / Optional | Alternatives, including null when declared |
| Literal | Exact scalar alternatives, distinguishing booleans and numbers |

Python float range and set hashability/equality retain the documented REST adapter
constraints. Strings are not implicitly parsed as numbers. Unknown fields and
missing required fields are rejected. No callable/class/annotation execution is
used to validate a request.

Omitted parameters are never forwarded, so Python applies the actual default.
`x: int = None` permits omission but rejects explicit null. `int | None` permits
explicit null. Default expressions are not evaluated or serialized. Mutable
Python defaults retain their ordinary identity and state.

Positional-only parameters become positional arguments; normal and keyword-only
parameters become keywords. A positional-only gap is invalid in both backends:
`f(a=1,b=2,/)` cannot receive `b` alone without injecting the omitted `a`.
`dependentRequired` documents this constraint. The same shared function implements
this rule for both transports.

Sync functions run in an AnyIO worker thread; async functions are awaited. This
is ordinary trusted execution, with no streaming, cancellation guarantee for
running sync code, sandbox or effect inference.

## Results and public errors

Finite JSON-compatible results remain structured values, including scalar and
array results on the 2026-07-28 protocol. A canonical JSON text block accompanies
them for clients consuming content. A Python `None` result is represented by null
and the text `null`; the SDK may omit its optional structured-content field.
Non-JSON values (including arbitrary objects, sets, tuples, non-string object keys
and non-finite floats) produce a controlled error rather than implicit coercion.

Declared return types do not validate results. Tools deliberately omit
`outputSchema`, because clients may enforce such a schema even if the server does
not. IR return enforcement remains `none`.

Public errors are deterministic `CallToolResult(is_error=True)` values:

| Failure | Public text |
| --- | --- |
| Unknown tool | `Unknown tool` |
| Input validation or positional gap | `Invalid tool arguments` |
| Unexpected source exception or unsupported result | `Tool execution failed` |

No exception repr, traceback, secret or local path is included. Server logs may
retain diagnostics. FastAPI HTTPException has no special meaning here and is
sanitized like any other unexpected exception.

## Runtime trust and integrity

Generation does not import source, run module code, decorators, defaults or
annotations, spawn subprocesses or access the network. Runtime startup is the
trusted-code boundary. Source and its execution environment must be trusted.

Before import, the shared loader verifies executable SHA-256, then compiles those
exact verified bytes, without rereading the source or loading cached bytecode.
Notebook bundles verify the exported Python used for inspection and retain the
original notebook. A mismatch fails before user import.

After import, the binding must be a Python function with the planned sync/async
form, names, parameter kinds and required/default presence, without variadics or
generators. No annotation string or deferred annotation is evaluated. Dotted
module identity is preserved under `source/`; loaded module-name conflicts fail
clearly instead of reusing an unrelated module.

This is unsigned content binding, not authenticity or provenance. Replacing a
manifest and executable together is not prevented. There is no runtime sandbox.

## Transports and optional features

One bundle supports runtime selection:

```bash
python server.py --transport stdio
python server.py --transport streamable-http --host 127.0.0.1 --port 8000
```

Streamable HTTP uses the SDK ASGI application at `/mcp`, served by Uvicorn. Local
binding and SDK DNS-rebinding protection are the default. Public deployment needs
an appropriately secured environment; this generator adds no authentication
policy. Stdio uses the SDK's stdio transport.

Integration tests use official `Client` APIs in process, over real stdio and over
real local Streamable HTTP. The default path negotiates 2026-07-28. The SDK's
`mode="legacy"` path is also tested on both transports with a structured object
result using 2025-11-25; Apizr contains no version negotiation branches. Earlier
protocols cannot express every modern structured scalar result, so the SDK owns
that compatibility conversion.

Effects are UNKNOWN. Tools omit safety annotations entirely: no read-only,
idempotence, destructiveness or world-access claim is inferred from a name.
No Resources, Prompts, Elicitation, Tasks, MCP Apps, Skills, extensions,
server-initiated domain logic or agent orchestration are registered.

## Artifacts, determinism and output safety

A Python bundle contains:

```text
server.py
apizr_runtime.py
source/<logical module>.py
source/<parent>/__init__.py  # when needed
capability-ir.json
readiness.json
mcp-tools.json
apizr-mcp.json
requirements.txt
```

Notebook bundles also contain `notebook.ipynb`. The independent `apizr.mcp/v1`
manifest records protocol/SDK assumptions, source/executable digests, IR/readiness
digests, invocation contracts, tool names/schemas and hashes of every other file.
Its own digest is excluded. All JSON keys and artifact names are sorted; no host
paths, timestamps or random IDs are added. Original input bytes remain unchanged.
Dependency ranges are deterministic text, not a runtime dependency lock.

The shared output writer rejects non-empty directories, overwrites, traversal and
symlink components. Directory-descriptor/no-follow support is required (tested
on Linux/macOS); unsupported hosts fail before writing. An I/O failure may leave
an incomplete new bundle, but does not authorize deletion of user files.

**MCP artifacts can later be externally attested; Apizr MCP generation does not
implement attestation.**

## Compatibility and validation

The REST fixture was pinned before extraction. Its complete generated file set,
OpenAPI and manifest remain byte-identical. A small REST serialization adapter
restores its original import preamble and type spellings around the shared runtime
functions; it contains no duplicate invocation logic. Existing REST golden tests
pin the entire emitted runtime, not just selected fields. The original 14 legacy
artifacts and issue #28 remain independent.

The MCP golden uses the existing REST pricing source and commits only the small
Tool document and manifest; the manifest pins all generated code hashes. Tests
cover cross-backend input equivalence, Hypothesis determinism/defaults/selection/
source tampering, hostile non-execution, contradictory runtime bindings, actual
SDK clients and wheel installation outside checkout. CI runs Python 3.11–3.14,
strict Pyright and separate 90% branch-aware MCP/shared-interface coverage floors.
