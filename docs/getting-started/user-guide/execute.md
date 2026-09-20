# Execute trusted code with a local policy

**Experimental. This command executes trusted Python source. It is not a
filesystem or network sandbox.** It requires a POSIX host (Linux or macOS) for the
local-process backend. Static inspection and REST/MCP generation still do not run
source, and their generated runtimes have not been migrated to this backend.

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
