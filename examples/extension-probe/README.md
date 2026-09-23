# Local extension packaging probe

This dependency-free package is a V04-01 test fixture, **not a public plugin**.
Do not publish it. It accepts only the private `apizr.extension-probe/v1` describe
request on stdin and emits one JSON response. It neither imports Apizr nor
executes application code.

From the repository root, use an already installed uv and Python:

```sh
uv run --locked python scripts/smoke_extension_packaging.py --work-dir /tmp/apizr-extension-demo
```

Use a fresh external directory. The driver builds and installs the core and this
package into separate environments, invokes the installed core from outside the
checkout, and retains `evidence.json`. See the
[ADR](../../docs/architecture/extension-packaging-v04.md) for the contract, trust
limits, real Homebrew recipe and cleanup. A separate process is not a sandbox.
