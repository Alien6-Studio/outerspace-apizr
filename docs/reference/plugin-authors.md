# Package an extension for Apizr

!!! warning "0.4 development — not released"

    Stable is 0.3.0. Use the [candidate installation](../getting-started/install.md#evaluate-the-040-candidate)
    for this page's 0.4 commands; they are not available in stable 0.3.0.
    The [development setup](../development/0.4.md#install-a-development-wheel)
    is for contributors building their own evaluation wheels.

A plugin is trusted code in a separate Python environment. Its public interface
is a wheel manifest plus the existing **`apizr.extension/v1`** request/response
contract. No registration decorator, SDK or internal core import is needed.

## Declare and package the entry point

Include `apizr-extension.json` at the wheel root:

```json
{
  "schema": "apizr.extension-manifest/v1",
  "name": "apizr-extension-probe",
  "version": "0.0.0",
  "module": "apizr_extension_probe.runtime",
  "protocol": "apizr.extension/v1"
}
```

The canonical name and exact version must agree with wheel filename and METADATA.
The module must be runnable with `python -m`. Build a wheel, not an editable
checkout. The existing
[packaged example](https://github.com/Alien6-Studio/outerspace-apizr/tree/master/examples/extension-probe)
shows the build configuration, manifest and a dependency-free implementation.
Its `runtime.py` accepts typed `DescribeArguments`, returns a structured result,
refuses an unknown operation and writes diagnostics only to stderr. The old
prototype `__main__` entry point is retained for historical tests; **use the
manifest's runtime module**, not that private prototype protocol.

## Receive one request and return one response

Follow the [wire contract](extension-invocation.md#wire-protocol-apizrextensionv1)
for the exact request, success and error fields. Copy the protocol, request ID
and operation from the validated request. Read a bounded UTF-8 JSON object from
stdin through EOF; produce exactly one finite JSON response on stdout and exit.
Never log to stdout. Do not echo secrets in diagnostics or error objects.

An unsupported operation returns `status: "error"` with `error.code` and
`error.message`; it is not a successful result. The core validates correlation,
protocol, duplicate keys and finite JSON, and maps remote failures to a redacted
`PluginFailed`. It never forwards raw plugin stderr or error contents.

The caller controls argument/output limits, deadline and cancellation through
[the invocation API](extension-invocation.md). No secret environment variables
are inherited by CLI invocation. A process group is cleaned on failure, but
independently detached descendants are outside that guarantee. This is **not a
sandbox**; a plugin runs with the user's privileges.

## Declare dependencies without installing into the core

Put Python requirements in wheel METADATA. For installation with dependencies,
provide an exact, hashed requirements file and local wheelhouse containing the
complete transitive closure. Use the
[existing supported requirements format](local-extensions.md) and archive rules:
no source builds, editable paths, direct dependency URLs, startup `.pth` files,
`sitecustomize` or `usercustomize`. Only the primary plugin needs an Apizr manifest.
uv installs offline into the plugin environment and checks dependency constraints.

A [catalog entry](plugin-catalog.md) can then be generated from those actual
artifacts. External tools such as Docker are prerequisites, not Python dependencies
that the catalog installs. Do not treat profiles as permission policies.

## Run the example outside the checkout

Use installed uv and Python with the existing packaging qualification:

```sh
uv run --locked python scripts/smoke_extension_packaging.py \
  --work-dir /tmp/apizr-author-proof
```

Choose a new temporary path. The driver builds real wheels, installs core and
example in separate environments, invokes the manifest module from outside the
checkout and checks that the core is unchanged. `invoke_installed.py` demonstrates
successful `describe` and refusal of an unknown operation using only public APIs.
The example requires no optional core imports.

This one-request extension protocol is **not MCP**. The optional `apizr-mcp`
plugin additionally exposes a persistent stdio server, managed by
[`apizr mcp serve`](apizr-mcp-server.md). A generated business MCP server is a
separate bundle; neither transport changes this extension contract.
