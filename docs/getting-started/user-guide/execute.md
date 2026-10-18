# Execute trusted code with a local policy

**Experimental. This command executes trusted Python source. It is not a
filesystem or network sandbox.** It requires a POSIX host (Linux or macOS) for the
local-process backend. Static inspection and REST/MCP generation still do not run
source. Generated REST/MCP runtimes remain direct by default and can
[explicitly opt into this backend](../../architecture/governed-transport-runtime-v1.md).

Create `sample.py`:

```python
def total(prices: list[float], *, tax: float = 0.2) -> float:
    return sum(prices) * (1 + tax)
```

Create `args.json` containing `{"prices": [10, 20]}`, then run from the checkout:

```sh
uv run apizr execute sample.py total \
  --arguments args.json \
  --policy examples/policies/local-default.json
```

The result is a JSON envelope with `status: "success"` and `value: 36.0`. The exit
code is zero for success and one for a controlled failure. Argument-parser errors
use exit code two. Select exactly one capability by name or full IR ID. Add
`--module-name project.pricing` to bind an explicit logical module. `.ipynb` inputs
use the same static notebook transformation as inspection; only the worker runs
the transformed module.

The default policy permits host filesystem, network and subprocess access, but
starts with a clean inherited environment, a fresh working directory, a 5-second
wall limit and 1 MiB input/output limits. A minimal policy file can contain `{}`;
all defaults are explicit in canonical policy serialization.

To allow selected environment variable **names**, use:

```json
{"environment": {"inherit": false, "allow": ["LANG", "TZ"]}}
```

Do not put credentials or variable values in policy files. Missing allowed names
are omitted. `inherit: true` explicitly passes the whole parent environment and
cannot be combined with an allowlist. User code can intentionally return data it
can access; sanitized failure diagnostics are not a secret-filtering service.

A timeout kills the worker process, including ordinary descendants in its process
group. It does not just cancel an async task. Every call starts a fresh process:
module globals and mutable default state reset. A fresh working directory does
not prevent access to other host paths. Detached descendants and memory usage are
not contained; only trusted code is suitable for this backend.

Requests such as `{"network":{"mode":"deny"}}`, filesystem sandboxing or
subprocess denial are refused before launch because this backend cannot enforce
them. `examples/policies/strict-known-effects.json` also intentionally refuses
capabilities whose required effect knowledge remains unknown.

Input validation preserves omitted defaults, explicit-null distinctions and
positional/keyword semantics. Results must be finite JSON values; unsupported
objects are not stringified. Exceptions return sanitized status codes, not their
text or worker stderr. Source tampering and callable shape mismatches fail before
invocation. Unknown capability names are invalid input; non-eligible capabilities
and unsupported policies are refused.

See [Execution Policy v1](../../architecture/execution-policy-v1.md) for the exact
protocol, digest chain, controls, limits and trust boundary.

## Advanced: explicit OCI container execution

The independent OCI backend adds Linux container filesystem/network and resource
boundaries. It requires a trusted Docker Engine, POSIX supervisor and an explicitly
prepared worker image. REST/MCP generation can explicitly select this backend with a v2 policy; see
[governed OCI transports](../../architecture/governed-oci-transports-v2.md).

From the repository, deliberately build a local fixture image:

```sh
uv build
uv run python scripts/build_worker_image.py dist/*.whl --output /tmp/worker-image.json
```

This preparation step can download the base image and hash-locked dependencies.
It prints the immutable image ID and platform. It does not publish an image or
include user source. Copy those values into the explicit invocation (replace the
placeholder with the complete ID; use the platform printed by the build):

```sh
apizr execute sample.py total --arguments args.json \
  --policy examples/policies/container-default.json \
  --runtime-image sha256:<full-64-character-local-image-ID> \
  --runtime-platform linux/amd64
```

Execution never pulls. Missing images return `runtime_image_unavailable`. V2
requires `schema_version: "apizr.execution/v2"`; `{}` still selects local v1.
The container policy defaults to network deny, read-only filesystem/bundle,
non-root execution, 256 MiB memory, one CPU, 64 PIDs and 16 MiB `/tmp` scratch.
Use `/tmp` for writable files. `resources.cpu_millis` expresses thousandths of one
CPU, independently of `limits.wall_time_ms`. Environment allowlists work as in
v1; whole-environment inheritance remains unsupported. For explicit subprocess
denial, use the [strict OCI profile](../../architecture/subprocess-deny.md) with a
current worker image. This profile also prohibits new threads.

Results use `apizr.execution-result/v2`; timeout, OOM evidence (`resource_limit`),
worker failures and cleanup failures are sanitized. Default allow-mode containers
contain subprocesses and detached children. Neither mode establishes a VM boundary. The daemon, kernel and selected worker image must be trusted.
See [OCI container runtime v1](../../architecture/oci-container-runtime-v1.md) for
exact controls, version boundaries, failure semantics and limitations.
