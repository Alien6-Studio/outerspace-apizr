# Governed OCI transport bridge v2

The original backend contract described here is unchanged. The 0.3 development
line also provides an opt-in [strict OCI subprocess-deny profile](subprocess-deny.md)
with a separate worker protocol; v1 static adapters retain their original guarantees.


REST and MCP can explicitly select the existing OCI-container executor. This is a
transport integration; the independently validated [OCI backend](oci-container-runtime-v1.md),
Capability IR, Readiness and shared invocation contract retain their semantics.
Direct execution remains the default. [Local-process governed bundles](governed-transport-runtime-v1.md)
remain byte-identical v1 bundles and do not require or probe Docker.

## Contracts and dispatch

OCI generation uses `apizr.execution-bundle/v2`. It explicitly binds:

- backend `oci-container` / `apizr.oci-container/v1`;
- policy `apizr.execution/v2` and its digest;
- provider `apizr.docker-engine/v1` and immutable image/platform configuration;
- one serialized `apizr.runtime/v2` plan, path and digest per selected capability;
- the unchanged REST/MCP transport-contract digest and every emitted artifact hash.

Local bundles remain `apizr.execution-bundle/v1`, with no automatic conversion.
REST/OpenAPI and MCP Tool definitions are unchanged across modes. An OCI plan's
inner worker plan binds capability identity, source/executable, IR, Readiness and
interface; its outer plan binds container policy and image/provider configuration.
No host paths, daemon endpoint, container IDs, timestamps or environment values
are inserted into these contracts.

The generator chooses one built-in bridge from the explicit typed policy. V1 uses
the unchanged local bridge; v2 uses `apizr.governed_oci`. Unknown versions and
inconsistent options fail closed. There is no registry, plugin system or dynamic
provider loading. Separate v2 adapter files preserve existing embedded v1 bytes;
they only translate transport requests/results, not Docker execution semantics.

## Generation and standalone runtime

Generation validates policy, controls, immutable full local image ID syntax,
platform, selection and linked inspection/contracts. It never probes Docker,
acquires an image, starts a worker, imports source or contacts a network. The same
inputs produce identical files regardless of output directory or Docker presence.
Actual image availability is a deployment concern, not a build-host fact.

The existing embedding mechanism copies the reviewed OCI models/planner,
provider/Docker implementation and supervisor, together with shared typed
validation/worker/protocol modules. Imports change from `apizr` to
`apizr_governed`. Tests compare OCI embedded source with installed source verbatim
apart from that import rewriting. Shared manifest/path utilities and Inspection
are copied by definition, using the existing embedding mechanism. No analyzers,
notebook exporter, legacy pipeline or unrelated generators are shipped.

Generated REST/MCP runtimes need only their generated Python requirements and the
Docker CLI/daemon. `outerspace-apizr` need not be installed in the **transport
server environment**. The separately prepared trusted worker image provides its
reviewed worker implementation; it is not downloaded or rebuilt by the bundle.

## Startup and invocation

Before serving, the v2 bridge anchors the transport manifest, validates bundle and
artifact hashes, required embedded files, policy and per-capability plan digests,
image identity, source/IR/readiness/interface linkage and the exact capability set.
It then probes the real Docker provider and selected local image. Missing Docker,
unsupported host controls, missing/wrong image/platform, missing worker label or
image volumes prevent startup. There is no partially operational API or fallback.

The transport process never imports source. Real server-process audit hooks in
REST, MCP stdio and MCP Streamable HTTP tests reject source imports/execution;
only the container worker executes it. Docker activity begins at runtime.

Plans and bound source bytes are cached at startup, not generated from requests.
Before each call every artifact and the anchored manifest are checked again. The
selected cached plan goes to the unchanged OCI executor, which retains its own
content-binding validation and provider checks. No alternate eligibility analysis
or fresh request-time plan generation is introduced by the bridge.

Each valid call creates one fresh container and uses the existing framed JSON
worker protocol. No pools or long-lived source workers. The backend retains all
mandatory isolation controls, `--pull=never`, argument/result byte limits and
explicit removal. Invalid arguments cannot start a capability container.

## Public result mappings

| Executor status | REST | MCP |
| --- | --- | --- |
| success | 200, JSON result | Normal structured result |
| invalid_input | 422, `Invalid request arguments` | `Invalid tool arguments` |
| timeout | 504, `Execution timed out` | `Tool execution timed out` |
| resource_limit | 503, `Execution resource limit exceeded` | `Tool execution resource limit exceeded` |
| backend_unavailable, runtime_image_unavailable, cleanup_failed | 500, `Internal server error` | `Tool execution failed` |
| binding_failed, policy_refused, worker_failed, source_mismatch | 500, `Internal server error` | `Tool execution failed` |
| execution_failed, result_invalid, output_limit | 500, `Internal server error` | `Tool execution failed` |

Errors omit Docker stderr, paths, image/container IDs, daemon endpoint, source
exceptions and environment values. A cleanup failure is never an ordinary success.
Startup failures are explicit generic runtime errors before traffic is accepted.
Health means the server passed its startup checks; later provider outages are
sanitized per call. Successful application output can intentionally expose data
available to the function; it is not secret-filtered.

## State and controls

| Property | Direct | Governed local | Governed OCI |
| --- | --- | --- | --- |
| Fresh invocation state | No | Fresh process | Fresh container/process |
| Wall timeout | No | Yes | Yes |
| Clean/allowlisted environment | No | Yes | Yes |
| Network deny | No | No | Yes |
| General host filesystem containment | No | No | Yes |
| Hard memory limit | No | No | Yes |
| PID containment | No | Ordinary process group | Container namespace/cgroup |
| Absolute subprocess denial | No | No | No |

Module globals and mutable defaults persist in direct mode and reset in both
governed modes. Common stateless finite-JSON contract tests compare all six
transport modes plus local/OCI `apizr execute`, including omitted defaults,
explicit null and positional/keyword parameter kinds.

Environment values exist only at runtime. With the default clean OCI environment,
`APIZR_TEST_SECRET` in the server cannot be seen by capability code. An explicit
name allowlist permits it without placing its value in artifacts or Docker
arguments. The transport itself keeps its normal server environment/network;
isolation applies to the capability container.

## Integrity, isolation evidence and limitations

After startup, changing source, policy, plan/image metadata, bridge or embedded
provider/worker files fails the next invocation. Restoring the original bytes
permits a healthy call without restarting the server. Tests cover every category.
Replacing the entire trusted bootstrap/server or modifying live process memory is
outside this content-binding threat model. Digests are not authentication.

The required `oci-isolation` job reuses one deliberately built worker image for
explicit execution and transport tests. Real REST, MCP stdio and MCP HTTP calls
attempt host-listener and host-file access, inspect read-only source/root and
scratch behavior, and verify the Docker socket is absent. OOM/timeout/crash calls
are followed by healthy calls. PID exhaustion is bounded; a detached heartbeat
child is observed before timeout and its container is absent afterward. The job
also checks no invocation containers remain and installs the wheel outside the
checkout, running generated bundles without Apizr installed.

The Docker daemon/runtime/kernel and selected worker image remain trusted. Network
none still permits private loopback. Containers are not VM security boundaries.
Subprocess creation remains permitted but contained; absolute denial (#49),
Kubernetes, scanning, new isolation controls and attestation are out of scope.
Daemon outages can prevent confirmed removal, which the existing backend reports
as cleanup_failed. External supervisor crashes still require operator recovery.
