# Local extension packaging probe

This dependency-free package is a V04-01 test fixture, **not a public plugin**.
Do not publish it. Its original entry point accepts the private `apizr.extension-probe/v1` describe
request on stdin and emits one JSON response. It neither imports Apizr nor
executes application code.

On a disposable runner, from the repository root, use an already installed uv and Python:

```sh
uv run --locked python scripts/smoke_extension_packaging.py --work-dir /tmp/apizr-extension-demo
```

Use a fresh external directory. The driver builds and installs the core and this
package into separate environments, invokes the installed core from outside the
checkout, and retains `evidence.json`. See the
[ADR](../../docs/architecture/extension-packaging-v04.md) for the contract, trust
limits, real Homebrew recipe and cleanup. A separate process is not a sandbox.

The `apizr_extension_probe.runtime` module also implements the reusable
`apizr.extension/v1` protocol. `invoke.py` runs it through
`apizr.extension_runtime` using explicit limits and an empty child environment.
The original module entry point remains available for the packaging prototype.
See [the invocation API](../../docs/reference/extension-invocation.md) for the
protocol, cancellation, failure codes and process-cleanup limits.

The wheel also contains the versioned `apizr-extension.json` manifest. The
packaging proof installs it through `apizr plugins install`, lists its record,
and runs `invoke_installed.py` outside the checkout. See
[local installation](../../docs/reference/local-extensions.md) for the commands,
offline constraints and atomic inventory behavior.
