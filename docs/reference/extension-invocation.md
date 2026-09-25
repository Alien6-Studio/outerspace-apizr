# Invoke an installed extension

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel) and record its source commit.

`apizr.extension_runtime` invokes a **trusted, already installed** Python module
in a fresh process. It is independent of the CLI, `apizr.compiler`, project
configuration and historical `apizr.pipeline.v1` plugins.

## Python call

The caller supplies an absolute interpreter from a separately prepared
environment, an importable module with a `__main__` entry point (or runnable
module), an operation, JSON arguments, limits and an explicit environment:

```python
from pathlib import Path
from apizr.extension_runtime import Limits, invoke_extension

response = invoke_extension(
    Path("/absolute/extension-env/bin/python"),
    "apizr_extension_probe.runtime",
    "describe",
    {"source_digest": "example-digest"},
    limits=Limits(wall_time_ms=3000, max_stdout_bytes=4096, max_stderr_bytes=1024),
    environment={},
)
assert response.operation == "describe"
assert response.result == {
    "source_digest": "example-digest",
    "message": "demo extension reached",
}
```

No download, installation, `uv` call, plugin discovery or plugin import in the
core occurs during invocation. The interpreter path is not resolved through its
symlink: a venv interpreter must retain its environment identity. Each call uses
`python -I -B -u -m MODULE`, without a shell, with closed inherited descriptors,
a new POSIX session/process group and a fresh temporary working directory.

`environment` is the complete environment passed to the process. Nothing is
copied automatically from the parent's environment, including credentials, PATH,
HOME and Python-specific variables. Callers may explicitly provide variables a
trusted extension needs. Python isolated mode ignores Python environment options
and user-site packages; Python itself may initialize locale defaults.

To cancel a running call, pass `cancel=threading.Event()` and set that event from
another thread. An event already set refuses the invocation before launch.
The synchronous supervisor checks cancellation at intervals of at most 50 ms
between bounded pipe operations, including after the plugin closes its pipes.
No persistent activation is recorded and `apizr.toml` cannot load extensions.

## Wire protocol: `apizr.extension/v1`

This is a single-message JSON protocol, **not MCP**. The core writes one UTF-8
JSON object followed by a newline to stdin, then closes stdin. The plugin writes
one UTF-8 JSON response to stdout and exits. Whitespace around that one response
is allowed; logs belong on stderr. Duplicate object keys, non-finite numbers,
invalid UTF-8, extra JSON documents, unknown fields and incompatible versions are
rejected.

A request has exactly these fields:

```json
{
  "protocol": "apizr.extension/v1",
  "request_id": "0123456789abcdef0123456789abcdef",
  "operation": "describe",
  "arguments": {"source_digest": "example-digest"}
}
```

The core creates a fresh random 32-character lowercase hexadecimal request ID.
Operations use 1–128 characters, beginning with an ASCII letter and continuing
with letters, digits, underscore, dot or hyphen. Arguments are a JSON object.

A successful response has exactly:

```json
{
  "protocol": "apizr.extension/v1",
  "request_id": "0123456789abcdef0123456789abcdef",
  "operation": "describe",
  "status": "ok",
  "result": {"source_digest": "example-digest", "message": "demo extension reached"}
}
```

An application failure replaces `result` with an error object:

```json
{
  "protocol": "apizr.extension/v1",
  "request_id": "0123456789abcdef0123456789abcdef",
  "operation": "describe",
  "status": "error",
  "error": {"code": "unknown_operation", "message": "Unsupported operation"}
}
```

Error codes contain 1–128 characters and messages at most 1024. The core requires
both the request ID and operation to match before accepting either response.
The process must exit successfully for a result to be accepted. Application
errors and nonzero exits raise `PluginFailed`; remote codes/messages and stderr
are not included in host diagnostics. `result` is finite JSON, with any
operation-specific shape checked by the caller. The demonstration additionally
checks the returned digest against the artifact produced by the core.

## Limits and failures

`Limits` is a strict, immutable model; unknown fields and invalid types/bounds
are refused. Byte limits apply to the complete serialized request or each output
stream, not just the application value.

| Limit | Default | Allowed range |
| --- | --- | --- |
| `wall_time_ms` | 10000 | 1–600000 |
| `max_request_bytes` | 1048576 | 1–67108864 |
| `max_stdout_bytes` | 1048576 | 1–67108864 |
| `max_stderr_bytes` | 65536 | 0–67108864 |
| `cleanup_time_ms` | 1000 | 1–5000 |

Request encoding reuses the existing finite, bounded JSON encoder and rejects
oversized arguments before launch. Nonblocking stdin writes prevent a plugin
that does not read from blocking the host indefinitely. Stdout and stderr are
read concurrently in chunks no larger than the remaining allowance plus one
byte. The first excess byte aborts the call. Only bounded stdout is retained;
stderr is counted and discarded. Neither output is captured without a limit.

All invocation errors derive from `ExtensionError` and expose a fixed `code`:

| Exception | Code / meaning |
| --- | --- |
| `InvalidInvocation` | `invalid_invocation`: invalid arguments, module, environment or tampered limits |
| `PrerequisiteMissing` | `prerequisite_missing`: nonabsolute/missing/nonexecutable interpreter, launch unavailable, or unsupported platform |
| `ProtocolInvalid` | `protocol_invalid`: malformed, incompatible or mismatched response |
| `PluginFailed` | `plugin_failed`: nonzero exit, missing module, application error or pipe failure |
| `SizeLimitExceeded` | `size_limit`, with `stream` equal to `request`, `stdout` or `stderr` |
| `InvocationTimeout` | `timeout`: execution deadline exceeded |
| `InvocationCancelled` | `cancelled`: explicit cancellation observed |
| `CleanupFailed` | `cleanup_failed`: group signalling or direct-child reaping could not be confirmed |

Diagnostics never interpolate arguments, environment values, output, plugin
messages or executable paths. Sensitive arguments travel on stdin, not argv.
The API neither prints diagnostics nor exits the host process.

## Cleanup and trust boundary

On success or failure, the supervisor sends SIGKILL to the owned process group,
closes all three streams and reaps the direct child within the cleanup budget.
If the leader exits while ordinary descendants retain stdout/stderr, the group
is terminated and remaining bounded pipe data is drained. Cleanup failure is
reported even when another error first ended the exchange. A successful group
signal during the exchange is retained through final cleanup, including on error
or cancellation. It is not sent again to an already signalled group: macOS can
return `EPERM` while that group contains only unreaped zombies. This does not
suppress a failed signal; without a prior successful group signal (or `ESRCH`),
permission/reaping failures still produce `CleanupFailed`. Direct-child exit
alone never counts as successful group signalling. See the
[macOS cleanup diagnosis](../architecture/extension-cleanup-macos.md).

This is **not a sandbox**. Extensions run with the user's permissions and can
access files, network and processes available to that user, including the core's
files if they deliberately choose to. There is no filesystem, memory, CPU or
network isolation. Explicit environment transmission prevents accidental secret
inheritance; it does not prevent trusted code from accessing other user resources.

Descendants that detach into another session/group escape group cleanup. If they
retain a pipe, the host still stops at the deadline, closes its descriptors and
reports timeout, but does not claim to have killed the detached process. Orphaned
grandchildren are reaped by the OS, not by this API. Kernel tasks that cannot be
interrupted, OS process creation and temporary-directory filesystem cleanup are
not hard real-time operations. The execution deadline plus bounded child wait
is not an absolute wall-clock guarantee for those OS operations. POSIX Linux and
macOS are supported; no weaker Windows fallback is provided.

The existing worker supervisors are unchanged. This supervisor follows their
nonblocking-pipe/process-group pattern but separately handles stderr, cancellation
and bounded reaping rather than changing existing worker guarantees.

## Installed proof

[`examples/extension-probe/invoke.py`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/examples/extension-probe/invoke.py)
is the short runnable example. On disposable CI runners,
`scripts/smoke_extension_packaging.py` builds and installs the real core wheel
and the dependency-free demonstration wheel into distinct environments, copies
the example outside the checkout and runs:

```sh
/absolute/core-env/bin/python -I -B /temporary/invoke.py /absolute/extension-env/bin/python
```

The existing uv and Homebrew packaging jobs retain the original prototype proof
and additionally exercise the reusable API. Their evidence records the response,
incompatible-protocol refusal, installed distributions, and before/after core
inventories including bytes, permissions, links and added/deleted files. The
core cannot import the extension. Installers run only during this explicit setup
on disposable runners, never during invocation; do not update workstation
Homebrew dependencies to reproduce the CI job.
