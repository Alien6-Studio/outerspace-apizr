# Execution Policy v1 and governed local execution

`apizr execute` is an **experimental trusted-code execution command**. It starts
one fresh Python process per invocation. This is **not a filesystem or network
sandbox**. It runs with the caller's privileges and requires trusted source.
`inspect`, `generate rest` and `generate mcp` remain static and non-executing.
REST/MCP v1 retain their existing in-process runtimes by default;
[optional governed generation](governed-transport-runtime-v1.md) delegates calls to
this same worker implementation.

## Boundary and contracts

`apizr.execution` consumes a validated inspection, selected capability identity,
original source bytes, executable bytes (for notebooks), and an execution policy.
It uses the shared `apizr.interfaces.InvocationContract`, planner, argument
validation, exact-byte source loader and callable verification. It does not infer
eligibility, annotations or effects again. Readiness remains the authority for
`can_generate_interface`; execution policy expresses separate runtime requirements.

Modules separate typed policy/backend capabilities (`policy.py`), bound plan and
result (`model.py`), validation (`planner.py`), canonical serialization, framed
JSON (`protocol.py`), parent supervision and worker execution. `execute_cli.py`
connects the explicit command to these APIs. No backend registry or plugin system
is introduced; a stronger future backend must declare its own version and actual
controls without changing interface semantics.

| Contract | Version |
| --- | --- |
| Policy | `apizr.execution/v1` |
| Backend capabilities | `apizr.backend/v1` |
| Local backend | `apizr.local-process/v1` |
| Runtime plan | `apizr.runtime/v1` |
| Public result | `apizr.execution-result/v1` |

## Enforced and unsupported controls

`local_capabilities()` provides a typed machine-readable declaration. This backend
is available on POSIX hosts (tested on Linux and macOS), where pipe selectors and
process groups are available. Other hosts are refused before worker launch.
This does not change Apizr's advertised Python 3.11–3.14 range or claim that other
Apizr commands require this backend.

| Control | Local-process v1 behavior |
| --- | --- |
| Wall time | Mandatory monotonic deadline; kill worker/process group with SIGKILL, reap direct child and close pipes |
| Input bytes | Bound canonical invocation JSON before spawning, validate again in worker; CLI also bounds the argument file |
| Output bytes | Bound complete response JSON in worker and parent, including framing length checks before accepting payload |
| Environment | Empty inherited map by default; explicitly allow named variables, or explicitly opt into full inheritance |
| Working directory | Fresh temporary directory for each call, removed after completion |
| Network denial | Unsupported; requested denial refuses planning |
| Filesystem sandbox | Unsupported; requested sandbox refuses planning |
| Subprocess denial | Unsupported; requested denial refuses planning |

The policy defaults are 5,000 ms, 1 MiB input and 1 MiB output. Size limits count
UTF-8 canonical JSON including its final newline; output includes the result
envelope, but excludes the eight-byte frame header. Output has a minimum of 128
bytes so controlled error envelopes fit. Maximum configurable input/output is
16 MiB; maximum wall time is one hour. The private request frame has a separate
64 MiB ceiling because it also carries the bound planning evidence.

A timeout is process termination, not coroutine cancellation. Timing includes
worker startup and protocol exchange; operating-system process creation and
scheduling are not real-time guarantees. The parent kills ordinary descendants
remaining in the worker's process group and waits for the direct child. A
subprocess deliberately creating a separate session can escape that group:
subprocess containment is **not** a supported control. There is no memory limit,
CPU allocation limit, PID limit, filesystem restriction, syscall filtering,
privilege drop or mount restriction. A large user allocation can happen before
JSON encoding; byte limits govern the protocol, not the worker's address space.
Host file/network access and subprocess creation are intentionally tested as
possible. Stronger controls are tracked in [issue #45](https://github.com/Alien6-Studio/outerspace-apizr/issues/45).

No Python monkeypatch is presented as an isolation mechanism. Unsupported policy
fields are rejected, and supported vocabulary requesting unavailable enforcement
fails closed. The model has no `best_effort` escape hatch.

## Effects and deterministic planning

`effects.require_known` is a sorted set of IR effect names. If any required effect
is `UNKNOWN`, planning refuses with `unknown_required_effect`. This is a knowledge
requirement, not a claim that a known effect is safe or absent. Current readiness
and IR effects are unchanged. The strict example intentionally refuses currently
unknown network/filesystem-write effects.

`policy_bytes` and `plan_bytes` use canonical sorted UTF-8 JSON with one trailing
newline. `policy_digest` and `plan_digest` compute external SHA-256 digests. The
plan binds source and executable digests, logical module, capability identity,
IR/readiness digests, shared interface and its digest, policy and its digest, and
backend version. It retains the validated inspection evidence so the worker can
revalidate the complete binding without source analysis. Independently supplied
mismatched objects are rejected. Golden policy/plan files and property tests check
byte stability on the supported Python matrix.

No policy/plan contains PID, timestamp, host name, temporary path, random ID or
environment values. Environment allowlists contain **names only**, sorted and
deduplicated. Runtime results are separate from deterministic planning artifacts.
Execution plans are attestable artifacts, not attestations. There is no receipt,
signature, Continuum Attest dependency or provenance verification.

## Parent, worker and protocol

The parent validates JSON input using the shared contract before starting user
execution. It writes source bytes into a temporary bundle and starts the installed
interpreter using an argument array: `python -I -m apizr.execution.worker`.
There is no shell, pickle or marshal. Isolated mode excludes the current directory,
user site packages and Python startup environment overrides; the installed Apizr
environment remains trusted. The supervisor never imports the target module.

Stdin carries one eight-byte unsigned big-endian payload length followed by one
JSON request. Stdout carries exactly one similarly framed response. Nonblocking
pipe supervision bounds reads, rejects excess/truncated/malformed data, detects
abnormal exit and applies the deadline even when a worker closes pipes but keeps
running. The worker reserves a non-inheritable output descriptor and redirects
ordinary stdout to stderr. The parent discards stderr, so user prints, tracebacks
and exception text are not forwarded as public diagnostics. This protocol is not
an adversarial security boundary against trusted code deliberately inspecting or
rewriting its own process descriptors.

Before importing, the worker validates the request/plan digest chain and exact
executable bytes. The shared loader compiles the verified bytes rather than a
cached pyc or a second read. Notebook execution uses the statically transformed
Python digest. After import, shared binding verification checks symbol/function,
sync/async form, absence of generator/variadics, parameter names/kinds and default
presence, without evaluating annotations. Source import itself is the trusted-code
boundary: module initialization, decorators and default expressions execute there.

The worker reconstructs positional-only and keyword-only arguments with the
existing shared semantics. Omitted defaults remain omitted; explicit null must
satisfy the annotation. Sync calls run directly; async calls run using the worker's
own event loop. No thread is used to interrupt user code. Each call starts afresh,
so module globals, environment changes and mutable defaults do not persist.
This intentionally differs from current REST/MCP in-process state lifetime;
[optional governed transport integration](governed-transport-runtime-v1.md) preserves this difference explicitly.

## Results and failures

Successful values must already be finite JSON data: null, bool, int, finite float,
str, lists and dictionaries with string keys. Sets, tuples, bytes, arbitrary
objects, non-string keys and non-finite floats fail conversion, matching the
conservative MCP result semantics. Return annotations do not enforce outputs.

Stable result statuses are `success`, `invalid_input`, `timeout`, `worker_failed`,
`binding_failed`, `policy_refused`, `result_invalid`, `execution_failed`,
`output_limit` and `source_mismatch`. Failure values are null. No exception repr,
traceback, stderr, PID or private runtime path is included. User-selected successful
return values are application data: trusted code can intentionally return anything
it can access, including explicitly allowed environment data. Sanitized diagnostics
are not data-loss prevention.

Real process tests cover sync/async, non-cooperative loops/sleep, crashes, noisy
stdio, framing failures, source tampering, binding conflicts, permitted host
access, environment filtering and state reset. Tests have hard outer timeouts.
Hypothesis checks canonical policy/plan determinism, argument transport, finite
JSON, source mutation, output boundaries and allowlists. Strict Pyright and separate
branch-aware 90% floors cover the package and worker/supervisor/protocol together.
