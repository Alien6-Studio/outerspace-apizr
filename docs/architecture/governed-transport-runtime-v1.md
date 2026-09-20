# Governed transport runtime v1

REST and MCP separate their interface from the strategy used to invoke it.
Generation without `--execution-policy` remains **direct**, with every existing
REST/MCP artifact byte preserved. Supplying a policy explicitly opts into the
**governed** local-process runtime. Both modes execute trusted code. Governed mode
is **not a filesystem or network sandbox**.

## Contracts and versioning

Capability IR v1, Readiness v1 and `InvocationContract` have no execution fields or
changed semantics. `apizr.rest/v1` and `apizr.mcp/v1` retain their route/Tool contracts;
OpenAPI and `mcp-tools.json` are byte-identical between modes for the same selection.
Execution strategy is separately declared by `apizr.execution-bundle/v1`, binding
`apizr.execution/v1`, `apizr.runtime/v1` and `apizr.local-process/v1`.

The original interface artifacts did not encode a mandatory process lifetime.
Direct mode preserves their historical lifetime; the separately versioned,
explicitly selected execution policy declares the governed lifetime. No silent
version reinterpretation or REST/MCP v2 is introduced. Canonical transport
manifests keep their existing shape: the artifact hash map binds the new execution
bridge and its files. The CLI presentation adds `execution.mode` (`direct` or
`governed`); governed presentation also names policy/backend versions. Existing
`schema_version` and `files` fields remain available.

## Runtime reuse and embedding

`apizr.governed.embedding` copies the installed execution implementation into
`apizr_governed/`, changing only package imports. Framing, supervision, timeout,
environment filtering, worker lifecycle, exact-byte loading, callable verification,
argument reconstruction, output conversion and error sanitization are shared with
`apizr execute`. There is no REST/MCP-specific worker or manual fork of that logic.

The embedded dependency closure contains the typed IR/Readiness/interface models,
canonical serializers and plan validators required to validate complete RuntimePlans.
It includes interface type lowering to verify linkage to the IR, never source
analysis or a second eligibility policy. The `Inspection` model definition is
copied verbatim from the installed module; analyzer/reporting entry points and
source-AST classification are omitted. Package initializers are empty. No source
analyzer, notebook exporter, legacy generator or documentation is copied. Only the
selected REST or MCP adapter is included.

The bootstrap loads the explicit embedded package with importlib; it does not
modify `sys.path`. A worker starts using an argument array with isolated Python:
`python -I <bundle>/execution/worker.py`. It activates that same package and runs
the same worker implementation in the fresh invocation directory. Generated
requirements add the reviewed Pydantic 2 floor used by the typed validators; they
never require `outerspace-apizr`. Standalone REST and MCP are tested in environments
without Apizr; MCP also works without FastAPI installed.

## Artifacts and content bindings

A governed bundle adds:

```text
execution/
    bundle.json
    policy.json
    plans/<capability-name>.json
    worker.py
apizr_governed/
    capabilities/       # typed validation models, no source analyzer
    readiness/          # typed validation models, no assessment engine
    interfaces/         # contract validation and shared invocation
    execution/          # the shared execution implementation
    governed/           # bundle validation and the selected adapter
    inspection.py       # the inspection value model only
```

The bridge declares its schema/backend/transport, policy path and digest, transport
contract digest, and a mapping from each selected capability ID to its plan path
and digest. Exactly one validated RuntimePlan is emitted per selected capability.
Its artifact map hashes all non-manifest files, including policy/plans, executable
source, IR/readiness, embedded code and public interface document. The transport
manifest hashes the bridge as well. Neither manifest hashes itself; there is no
circular digest dependency.

The chain remains independently visible: source → IR → readiness → interface →
policy → per-capability runtime plan → execution bundle → transport artifact map.
Canonical bytes contain no build-host availability, timestamp, PID, hostname,
absolute deployment path, runtime environment values or random identifier.
Plans are content-bound artifacts, not signed attestations. No Continuum Attest,
signatures or SLSA fields are introduced.

## Build host versus runtime host

Static generation calls execution planning with `check_availability=False`. This
checks requirements against the declared local-process contract, not `os.name` on
the build machine. Unsupported network/filesystem/subprocess controls and unknown
required effects still refuse generation. Runtime validation always checks actual
backend availability. No host availability flag is serialized into the plan.

The backend currently requires POSIX facilities, tested on Linux and macOS.
Unavailable deployment hosts fail at server startup before serving requests.
Output writing independently retains its existing filesystem-capability and
exclusive-directory checks; host-independent artifact bytes do not promise that
all host filesystems support safe writing. Python support remains 3.11–3.14.

## Startup and invocation

`GovernedRuntime` checks the transport manifest, bridge version/hash, backend,
policy digest, plan digests, artifact presence/hashes and source/IR/readiness/
interface linkage. Paths cannot escape the bundle root. It does not import user
source. REST routes and MCP Tools use the existing shared contracts.

Startup retains the transport manifest digest as an in-memory anchor. Every call
revalidates the bound artifacts before launching a worker, so source, policy,
plan, worker or manifest modifications become a sanitized call failure while the
server stays alive. Restoring the original bytes allows subsequent calls again.
The worker rechecks exact executable content and callable shape before invocation.
A bundled notebook retains its original bytes and executes its bound transformed
Python. Only the worker crosses the trusted source-import boundary.

These are content/integrity checks, not protection against an attacker who controls
the bootstrap, interpreter or all initial artifacts. Runtime code must be trusted
before it can validate data. The operating system and installed dependencies remain
trusted, and no authenticity guarantee is claimed.

Supervision runs in a transport thread to keep its event loop responsive; user
code runs in its fresh process. There is no worker pool. Ordinary process-group
children are terminated during cleanup; deliberately detached descendants remain
outside the supported controls. Module/global/default state does not survive calls.

## Transport mappings

| Execution outcome | REST | MCP Tool result |
| --- | --- | --- |
| success | 200 with finite JSON value | Normal structured result |
| invalid_input | 422, `Invalid request arguments` | `Invalid tool arguments` |
| timeout | 504, `Execution timed out` | `Tool execution timed out` |
| Every other execution failure | 500, `Internal server error` | `Tool execution failed` |

All worker/binding/policy/result/output/integrity failures use this consistent
server-error rule; no internal worker status, traceback, stderr or private path is
forwarded. Invalid REST JSON also returns generic 422. Unknown MCP Tool names keep
`Unknown tool`. MCP SDK v2, protocol 2026-07-28, stdio and Streamable HTTP remain
supported; the executor has no MCP-specific semantics.

Request binding preserves positional-only/keyword-only arguments, omitted defaults
and explicit-null distinctions. Return annotations remain non-enforcing. Governed
REST deliberately accepts only finite JSON-compatible results; direct REST's
FastAPI encoder can serialize additional Python objects. Governed mode does not
coerce those objects. Source exceptions, including intentional framework HTTP
exceptions, cross the sanitized execution boundary rather than retaining direct
REST's special HTTPException behavior. Direct mode is unchanged.

## State, environment and limits

| Behavior | Direct (default) | Governed (opt-in) |
| --- | --- | --- |
| Source import | Server startup | Fresh worker per call |
| Globals / mutable defaults | Persist in server | Reset each call |
| Timeout boundary | Existing in-process behavior | OS process termination |
| Input/output protocol limits | Existing transport behavior | Execution policy limits |
| Source environment | Server environment | Clean/allowlisted worker environment |
| File/network access | Host access | Host access; no filesystem/network sandbox |

The server may inherit its environment normally; the worker receives only the
policy-selected names unless full inheritance is explicitly requested. Values are
never inserted into artifacts or failure diagnostics. Trusted code can deliberately
return values it can access; this is not a secret-filtering service.

Input/output limits bound the worker protocol, not the web server's HTTP body
buffering or total process memory. A fresh CWD is not filesystem isolation. There
are no memory cgroups, OCI/Docker execution, namespaces, seccomp, privilege/mount
restrictions, subprocess isolation or detached-descendant containment.

## Verification and deferred work

Direct artifact hashes are pinned to the pre-integration baselines. Governed
manifest goldens run on Python 3.11–3.14 and bind all emitted file hashes. Bounded
Hypothesis tests exercise determinism, argument parity, allowlists, source mutation
and output boundaries. A common conformance corpus runs through direct/governed
REST/MCP and explicit execution. Real REST, MCP stdio and MCP HTTP tests exercise
hangs, crashes, sanitization and tampering, then call a healthy capability again.
Audit hooks in real transport processes reject any target-source execution there.
Strict Pyright and a separate branch-aware 90% integration floor are required,
alongside all existing quality/security/coverage gates.

[Issue #44](https://github.com/Alien6-Studio/outerspace-apizr/issues/44) is the
opt-in transport integration addressed here. [Issue #45](https://github.com/Alien6-Studio/outerspace-apizr/issues/45)
remains open for genuine stronger host and detached-descendant containment.

An independent [v2 OCI transport bridge](governed-oci-transports-v2.md) is now available through explicit v2 policy/image options. This page and existing v1 bundles retain their local-process semantics.
