# OCI container runtime v1

This second backend executes one selected READY capability in a fresh Linux
container. It is available through `apizr execute` and `apizr.oci` Python APIs.
[Governed REST/MCP OCI bundles](governed-oci-transports-v2.md) reuse this backend
when explicitly selected. Direct and local-process generation remain unchanged.

## Boundaries and versions

The policy describes requirements; the provider implements launch mechanics.
`apizr.oci.provider.ContainerProvider` separates probe, creation, attached protocol
command, terminal-state evidence and removal. Docker Engine is the first trusted provider.
There is no Docker SDK dependency and no arbitrary Docker argument/mount option.

| Contract | Version | Meaning |
| --- | --- | --- |
| Existing policy | `apizr.execution/v1` | Stable local-process semantics |
| New policy | `apizr.execution/v2` | Typed resource/control vocabulary, explicit `oci-container` backend |
| Existing worker plan | `apizr.runtime/v1` | Bound invocation validated by the unchanged worker |
| Container plan | `apizr.runtime/v2` | Outer policy, image/provider and inner worker plan |
| Backend | `apizr.oci-container/v1` | Mandatory Linux container controls |
| Provider | `apizr.docker-engine/v1` | Docker CLI implementation |
| Public result | `apizr.execution-result/v2` | Existing statuses plus provider/resource/cleanup failures |

V2 currently accepts only `oci-container`; it is not an automatic migration or a
new interpretation of v1. The vocabulary is not Docker CLI syntax. A future
provider/version can implement the container contract. V1 policy, plan, worker,
protocol and governed bundle bytes remain unchanged.

OCI Runtime Specification [v1.3](https://github.com/opencontainers/runtime-spec/tree/v1.3.0)
is the conceptual Linux process/namespaces/mounts/cgroups boundary. Apizr does not
emit an OCI `config.json`, negotiate a runtime-spec version, or claim an OCI
conformance certification. Docker translates its engine configuration into runtime
controls. See the [Docker run reference](https://docs.docker.com/engine/containers/run/)
and [resource constraints](https://docs.docker.com/engine/containers/resource_constraints/).

## Plan and shared worker

Pure `apizr.oci.planner.plan` consumes Inspection, original source, optional
notebook executable, selection, policy and explicit `RuntimeImage`. It does not
probe Docker, import source, acquire images or run a process. It delegates interface
eligibility and effect requirements to existing planners. Unsupported controls
fail closed. Canonical bytes use existing sorted JSON serialization.

The outer plan binds the v2 policy digest, backend identity and runtime image
configuration. Its nested, hashed worker plan binds source, transformed executable,
IR, readiness and interface digests. The worker's v1 policy requests only the
limits, environment and effect controls it actually validates; it does not claim
to enforce containers. The supervisor reconstructs and compares the entire outer
plan before launch. The unchanged `apizr.execution.worker` then validates the
inner plan and exact source bytes, verifies callable shape, reconstructs arguments,
runs sync/async code and enforces finite JSON results.

No Docker-specific application protocol or duplicate capability worker exists.
The existing uint64-length-prefixed JSON request/response travels over attached
stdin/stdout, without a network endpoint. Byte/framing limits remain independent
of cgroup limits. Ordinary source stdout/stderr is not a response channel.

Plans contain no container names/IDs, paths to the host bundle, daemon endpoint,
probe output, timestamps or environment values. Runtime names are transient.
Golden plans use a synthetic full image ID, independently of local image builds.

## Runtime image and deliberate preparation

V1 accepts a **full local `sha256:<64 lowercase hex>` image ID**, verified by
`docker image inspect`, plus explicit `linux/amd64` or `linux/arm64` platform.
Mutable tags, abbreviated IDs and registry references are rejected. This is the
verified local image-ID form of immutable identity; registry-digest selection can
be added deliberately later. The exact ID/platform/provider enter the plan.

The image must provide `/usr/local/bin/python` (supported Python 3.11–3.14), the
installed Apizr worker and `apizr.oci.entrypoint`, and its Pydantic dependencies.
It must support UID/GID 65532, declare no image volumes, and carry
`org.apizr.worker.protocol=apizr.runtime/v1`. The label declares compatibility;
it is not authentication or proof of image contents. The selected image is trusted.
Apizr overrides entrypoint, working directory, user and health checks.

`scripts/build_worker_image.py` deliberately builds a local test image from a
wheel. Its temporary context contains only that wheel, generated Dockerfile and
the hash-locked Pydantic dependency closure from `uv.lock`. It does not include
user source, push an image or perform registry authentication. Preparation may
acquire the specified base image and dependencies; invocation never does.

Execution uses `docker create --pull=never`. Absent, mismatched, incompatible or
wrong-platform images yield `runtime_image_unavailable`. No registry fallback or
implicit update is attempted. The image digest binds selected content, not build
provenance; no signing, SLSA or attestation implementation is included.

## Mandatory controls

Every invocation enforces these controls with no escape hatch:

- Unprivileged container, UID/GID 65532, all Linux capabilities dropped and
  `no-new-privileges` enabled.
- Read-only root and one read-only private bind mount at `/bundle`, containing
  exactly the original input and executable source tree. No repository/home/host
  root, Docker socket, arbitrary device or policy-provided mount is exposed.
- Private PID/IPC/cgroup namespaces; no host network namespace. Network mode
  `none` denies normal external/host connectivity; loopback still exists.
- `/tmp` is bounded tmpfs with `nosuid,nodev,noexec`, mode 1777. `/dev/shm` is
  explicitly limited to 64 KiB. Standard container `/dev` and kernel pseudo-files
  still exist; this is not an empty filesystem. Scratch consumes the cgroup memory
  budget. Source-relative writes fail; use `/tmp` for writable scratch.
- Hard memory limit with combined memory+swap equal to memory (no extra swap),
  CPU quota and PID limit. CPU is integer thousandths of a CPU: `cpu_millis=500`
  translates to quota 50000 per period 100000. It does not replace wall timeout.
- Docker's builtin default seccomp profile must be advertised; missing or
  unconfined seccomp fails the probe. No custom syscall policy is claimed.
- No restart policy, health check or persistent Docker log capture.

Defaults: 256 MiB memory, one CPU, 64 PIDs, 16 MiB scratch, 5 seconds attached
execution, 1 MiB input/output. Bounds are typed, finite and conservative. Scratch
cannot exceed half the memory budget. Network inherit, environment inherit and
absolute subprocess denial are unsupported v2 requirements and fail closed.
Subprocesses are **permitted but contained** in the PID namespace/cgroup.

## Environment and trust

Only explicitly allowed names receive parent values. Docker reads those values
from its CLI environment (`--env NAME`); values are absent from command arguments,
plans, labels and automatic diagnostics. Before calling the shared worker, the
image entrypoint clears image/Docker-injected environment defaults and preserves
only the requested names. The Docker daemon can inspect container environment:
it is a trusted administrator, not a secret vault. Source can intentionally return
data it receives; successful application output is not secret-filtered.

The POSIX supervisor, selected worker image, Docker CLI/daemon, container runtime
and host kernel are trusted. Docker Desktop additionally trusts its Linux VM.
This is stronger containment than local processes, not a VM boundary for hostile
multi-tenant execution. Kernel/runtime compromise is outside the threat model.
Static planning/generation remain non-executing. `execute` crosses the explicit
runtime source-execution boundary.

## Lifecycle and failures

The provider checks Docker reachability, Linux mode, memory/swap/CPU/PID support,
seccomp and image compatibility separately from planning. Native Windows pipe
supervision is not supported; a Linux/macOS POSIX host can supervise Linux Docker.
Unavailable controls/flags/daemon yield a sanitized `backend_unavailable`.

A fresh, privately named container receives one request. The existing bounded
pipe supervisor enforces wall time while starting/attaching the worker. Every
post-create path runs explicit `rm --force --volumes` in `finally`, including
failed creation, source failure, malformed response, timeout and OOM. Removal
terminates descendants even after `setsid()`. There is no process pool, host-wide
kill heuristic or automatic removal that hides OOM evidence.

The attached invocation deadline includes Docker start overhead. Probe, create,
and removal have separate bounded CLI timeouts (10 seconds each);
cleanup retries up to three times. A daemon outage may prevent confirmed removal:
return `cleanup_failed`, never claim successful cleanup, and restore/manage the
trusted daemon before further work. Normal integration paths assert absence of
the exact invocation container after return.

Only reliable terminal Docker `State.OOMKilled=true` maps a failed worker to
`resource_limit`. A generic exit code alone remains `worker_failed`. Wall
expiration is `timeout` and bypasses terminal observation, even if subsequent
cleanup kills the container.

`ContainerProvider.final_state` returns internal typed evidence (`running`,
`status`, `oom_killed`, `exit_code`) or no evidence. Docker validates the four
[documented State fields](https://docs.docker.com/reference/api/engine/version/v1.52/)
strictly, requiring their actual JSON types. Additional unused Docker fields are
ignored. Evidence is terminal only when `Running=false` and `Status` is `exited`
or `dead`. This representation is not added to any public result or manifest.

The provider observes only a generic `worker_failed` result, before removal.
The default monotonic observation budget is **1 second**, independent of the
capability wall deadline. Each inspect subprocess gets at most **250 ms**, capped
by the remaining budget. Nonterminal, inconsistent, malformed or unavailable
observations retry after at most **50 ms**, without busy waiting. A terminal OOM
returns immediately. An ordinary terminal exit such as 23 returns immediately.
Exit 137 (and exit 0 without a valid worker response) leaves room for delayed OOM
metadata until the budget expires; neither code is OOM evidence. Without positive
terminal OOM evidence the generic failure remains unchanged. An inspect failure
never exposes Docker stderr. Cleanup still runs in `finally`, and its failure
still takes precedence over classification.

Successful calls and supervisor timeouts perform **no extra inspection or sleep**.
An inconclusive failure adds at most a one-second observation budget, plus normal
OS process-creation/reaping and scheduler overhead; Python subprocess timeouts
cannot strictly bound those OS operations. Probe/create/removal budgets are
unchanged. There is no arbitrary supervisor sleep or GitHub Actions retry.

Issue [#57](https://github.com/Alien6-Studio/outerspace-apizr/issues/57) recorded
intermittent direct and MCP HTTP misclassification on Linux CI. Those failed runs
did not capture Docker State, so their exact event ordering is unproven. A
controlled running/false → exited/false/137 → exited/true/137 sequence reproduces
the old one-observation gap. Docker's
[OOM and exit event handlers](https://github.com/moby/moby/blob/master/daemon/monitor.go)
update state separately; attach completion alone is not a terminal-evidence
contract. Tests cover that sequence, transient inspection failures, strict JSON,
bounded waiting, ordinary exit 23, non-OOM exit 137 and timeout precedence.
Required OCI CI also checks every sample of 10 real direct OOM invocations and 5
per REST/MCP stdio/MCP HTTP transport, with repeated non-OOM/timeout controls and
removal assertions. Passing local samples alone do not establish reproduction
of the original Linux CI race.

This fix changes three embedded OCI source files and their hashes in generated
OCI bundles (including the enclosing manifests). Existing bundles must be
regenerated to receive it. Public schemas/versions, policies/plans, direct/local
bundles and legacy artifacts remain unchanged.
Failure results contain only stable statuses and null values: no provider stderr,
source exceptions, host paths, daemon addresses, IDs or environment values.

## Evidence and compatibility

Real Docker tests inspect UID, `/proc/self/status` capabilities/NNP/seccomp,
read-only mount flags, cgroup v2 values and bounded scratch writes. They attempt
host-marker access and connections to a real host TCP listener; allocate beyond
a small memory limit; exhaust a bounded PID allowance; and observe a detached
child heartbeat before timeout then verify removal and loss of access afterward.
Unit tests additionally cover unavailable controls, image mismatch, unsupported
policy, deterministic planning, protocol and cleanup failures. Linux CI always
builds an explicit test image and runs the integration suite; optional local tests
skip only when no image configuration was supplied. Supplied but unusable images
fail, rather than silently skipping security checks.

| Guarantee | Local process v1 | OCI container v1 |
| --- | --- | --- |
| Wall deadline, input/output bounds | Yes | Yes |
| Filtered environment, fresh invocation | Yes | Yes |
| General host filesystem containment | No | Yes |
| External/host network deny | No | Yes |
| Hard memory, CPU quota, PID limit | No | Yes |
| Detached descendant containment | No | Yes |
| Non-root, capability drop, NNP | Not imposed | Mandatory |
| Absolute subprocess prohibition | No | No |

REST/MCP direct and governed output, execution v1 goldens, Capability IR,
Readiness, Interface Contract and the legacy generator remain byte-compatible.
Custom seccomp/subprocess prohibition, microVM isolation,
image publication/acquisition UX and resource scheduling remain deferred.
