# Governed repository execution

The original backend contract remains unchanged. An opt-in
[strict OCI subprocess-deny profile](subprocess-deny.md) adds a separate worker
protocol; v1 static adapters retain their original guarantees.


**Available in published stable 0.3.0.**

Repository exposure now supports direct, governed local-process and governed OCI
REST/MCP bundles. The requested backend must be explicitly compatible with every
selected Exposure Record. Generation never ranks backends or falls back to direct.
The existing Readiness eligibility restrictions remain in force.

| Mode | Invocation boundary | State between calls |
| --- | --- | --- |
| Direct | Trusted transport interpreter | Globals, imports and mutable defaults persist |
| Governed local | Fresh Python process and copied invocation directory | Reset each invocation |
| Governed OCI | Fresh container and read-only copied bundle | Reset each invocation |

## Independent contracts

`apizr.repository-runtime/v1` binds the complete Repository Interface and digest,
Exposure Plan digest, source-universe digest, exact capability ID, shared
InvocationContract and digest, bound effect snapshot, ExecutionPolicy v1 and digest.
The source-universe digest covers the canonical source manifest: each relative
source/bundle path, module, package identity, size and content hash.

`apizr.repository-runtime/v2` wraps that worker contract with ExecutionPolicy v2
and digest, explicit RuntimeImage and worker digest. The worker's execution context
records which exposure backend authorized it; it does not claim kernel enforcement.
A v1 worker authorized for OCI cannot be invoked as a local plan.

`apizr.repository-execution-bundle/v1` and `/v2` independently bind these plans to
REST/MCP manifests. They record the repository/exposure/transport-contract digests,
policy artifact, capability-ID-to-plan mapping and exact artifact hashes. v2 also
binds provider and runtime image. Plan filenames are SHA-256 hashes of capability
IDs. Public names are presentation; capability IDs authorize invocation.

The existing single-source runtime/bridge contracts and repository transport v1
contracts are unchanged. Omitting the execution policy produces the exact previous
direct artifacts. Committed schemas:

- [Repository runtime v1](../specs/apizr-repository-runtime-v1.schema.json)
- [Repository runtime v2](../specs/apizr-repository-runtime-v2.schema.json)
- [Repository bridge v1](../specs/apizr-repository-execution-bundle-v1.schema.json)
- [Repository bridge v2](../specs/apizr-repository-execution-bundle-v2.schema.json)

## Static generation and integrity

Generation consumes validated catalog, graph, readiness, exposure and interface
evidence. It does not execute project code, probe Docker, check runtime image
availability, inspect installed dependencies, run Git or connect to the network.
Unknown effects required by `effects.require_known` refuse planning; the execution
planner consumes the bound effect snapshot without inferring effects.

The generator prepares all plans and artifacts before staging and atomic output
publication. Output must be new or empty. Artifacts contain no build-host path,
PID, timestamp or hostname. Source/capability ordering and repository relocation
do not change the bytes.

At startup, the transport checks its manifest, all artifact hashes, repository
interface, upstream evidence, exposure policy, execution bridge/policy, each plan,
source manifest, source bytes and backend availability. It never installs the
project importer or imports selected/support project modules.

Before **every call**, it rereads the manifest against the startup digest anchor,
revalidates all emitted artifacts and their cross-bindings, then uses the verified
bytes to populate a fresh invocation root. No cached startup plan bypasses these
checks. A modified source, policy, plan, interface, worker or bridge produces a
sanitized failure; restoring the original bytes permits later calls. Hash binding
is integrity within the trusted bundle, not publisher authentication against an
attacker who replaces an entire bundle before startup.

## Worker and importer

Only the fresh worker installs the existing `RepositoryLoader`. It verifies the
exact source universe and imports the selected module using verified bytes,
including real package initializers, relative imports and synthetic namespace
parents. Undeclared local children and unchecked filesystem/bytecode fallbacks
remain refused. Unrelated modules are checked without executing their source.
An unexposed helper remains private even when selected code calls it.

The worker uses the shared framed protocol, input bounds, `verify_binding`,
`arguments`, sync/async invocation and finite JSON output rules. Source exceptions,
stderr, internal paths and daemon errors are not returned to clients. Public
results reuse `apizr.execution-result/v1` and `/v2`.

| Outcome | REST | MCP message |
| --- | --- | --- |
| Success | 200 | JSON result |
| Invalid input | 422 | Invalid tool arguments |
| Timeout | 504 | Tool execution timed out |
| OCI resource limit | 503 | Tool execution resource limit exceeded |
| Other failure | 500 | Tool execution failed |

## Local and OCI boundaries

Local execution reuses wall timeout, input/output limits, clean or allowlisted
environment, fresh working directory and process-group cleanup. It provides no
network denial, filesystem sandbox or absolute subprocess prohibition. Unsupported
controls fail closed. A missing local backend refuses startup/invocation.

OCI uses the same reviewed Docker launch implementation as single-source execution:
network none, read-only root, UID/GID 65532, dropped capabilities, no-new-privileges,
seccomp, private IPC/cgroup namespace, memory/CPU/PID limits, bounded scratch,
read-only `/bundle` and unconditional teardown. Only the fixed repository entrypoint
differs. There is no second security-flag list or generic Docker argument/mount/device
escape. This is container isolation, not a VM. PID limits do not prohibit subprocesses;
`subprocess_deny` remains refused under this original contract.

Repository OCI startup and invocation verify the immutable `sha256:<64hex>` image
ID, explicit Linux platform, existing worker compatibility and the additional label
`org.apizr.repository.worker.protocol=apizr.repository-runtime/v1`. An old image
with only the single-source label is insufficient. The development worker image
advertises both. There is no tag resolution, automatic pull or local fallback.
The dedicated entrypoint clears image environment, retains only explicitly allowed
names, changes to `/bundle` and starts the repository worker.

OOM is classified as `resource_limit` only when the provider reports a terminal
container with positive OOM evidence. Exit 137 alone is not sufficient. Timeout
classification and unconditional cleanup retain the existing semantics.

## Deployment responsibility

Standalone generated transports embed only the reviewed runtime dependency closure;
installation of `outerspace-apizr` in the transport environment is unnecessary.
They do not embed analyzers, repository scanners, graph builders, notebook conversion
or legacy generators. Local workers use that Python environment; OCI workers use
the explicitly selected image. External application dependencies must already be
installed there. Missing dependencies fail sanitized; nothing installs them for you.

Only Python source is packaged. Data/resources remain an explicit deployment concern.
Bundling the scanned source universe does not prove complete runtime dependency
closure or transitive safety. Code and dependencies must still be trusted.

## Verification

Tests pin every direct artifact hash against baseline #91 and preserve all existing
single-source goldens. Four governed manifest/bridge goldens cover local/OCI REST/MCP.
Audit hooks guard generation and actual REST, MCP stdio and MCP Streamable HTTP
transport processes. Real workers verify fresh globals/defaults/support-module state,
private helpers, package imports, tamper recovery, crash and timeout containment.
The mandatory OCI job runs those transports and reuses reviewed kernel isolation,
ordinary/detached descendant and repeated OOM probes. Both new packages have separate
90% branch-aware coverage floors and strict Pyright checks.

This completes the intended core 0.3 runtime flow. The repository is in its release-candidate
and product pass; publication remains a separate deliberate action.
