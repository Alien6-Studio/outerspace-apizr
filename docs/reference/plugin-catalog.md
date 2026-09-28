# Choose plugins from a catalog

For prerequisites and package availability, see [Install Apizr](../getting-started/install.md).

A **plugin catalog** describes available plugin artifacts. It is separate from
`apizr scan`'s catalog of Python capabilities. A **profile** selects exact plugin
versions; it contains no scripts, secrets, activation or execution permissions.

<span id="obtain-a-development-catalog"></span>

## Obtain a verified catalog

The Linux/macOS **MCP server plugin** CI artifacts contain `catalog/catalogue.json`,
`wheels/` (including `requirements/`) and the exported plans. Choose the artifact
for your exact Python/platform target and the source commit you intend to use.
These are development builds, not published releases or a hosted marketplace.
The core and three official plugins declare `0.4.0rc1`; use the source commit and
SHA-256 values to distinguish builds. A matching version string alone does
**not** establish artifact identity or qualification.

To prepare and qualify these artifacts yourself, from a development checkout
with uv and an installed Python, use a new directory outside the checkout:

```sh
uv run --locked python scripts/smoke_mcp_server.py --output /tmp/apizr-catalog-proof
```

Preparation explicitly builds the core and three plugins and obtains dependency
wheels. It then generates the catalog from those inspected bytes, exports the
profiles and tests an installed MCP server with a real client. Preparation may
use the network; **catalog commands do not**. The wheels are retained and are
not rebuilt between catalog generation and installation.

## Consult, choose and lock

Extract the matching `mcp-stdio-OS-python-VERSION` artifact and enter its
`_temp/mcp-proof/` directory. It contains `catalog/catalogue.json` and `wheels/`;
test/coverage reports occupy another subtree. Use the `apizr` executable installed with these artifacts:

```sh
apizr plugins catalog list --catalog catalog/catalogue.json --json
apizr plugins catalog show outerspace-apizr-mcp --version 0.4.0rc1 \
  --catalog catalog/catalogue.json --json
apizr plugins catalog resolve --profile mcp \
  --catalog catalog/catalogue.json --wheelhouse ./wheels \
  --output-dir ./plugin-plan --json
apizr plugins lock check --project plugin-plan/apizr.toml \
  --lock plugin-plan/apizr.plugins.lock.json --wheelhouse ./wheels --json
```

| Profile | Selected installations | Purpose |
| --- | --- | --- |
| `mcp` | `outerspace-apizr-mcp` | Persistent analysis MCP server |
| `oci` | `outerspace-apizr-oci` | Build and publish service images |
| `delivery` | `outerspace-apizr-oci`, `outerspace-apizr-attest` | Images and delivery receipts |

`list` reads metadata only. `show` requires an unambiguous entry for the exact
version and current target. Neither reads the wheels or invokes an external tool.
`resolve` checks the profile, target, hashes, manifests and archive protections,
then writes `apizr.toml`, unchanged requirements bytes and
`apizr.plugins.lock.json` using the existing lock creator. A successful result
says `compatibility: declared`, `artifacts: statically_verified` and
`installation: not_performed`.

Choose a **new** output directory: even an existing empty directory is refused.
The private staging directory is removed on error or interruption; only a
complete plan is published. Identical inputs and target produce identical files,
without machine-specific absolute paths or timestamps. The exported project has
`root = "."`; set your analysis root separately when using your own project.

## Install and activate explicitly

Review and trust the selected code before installing it. Hashes establish
integrity, not author trust. A catalog cannot grant execution authority.

```sh
apizr plugins sync --project plugin-plan/apizr.toml \
  --lock plugin-plan/apizr.plugins.lock.json --wheelhouse ./wheels \
  --plugins-dir ./trusted-plugins --json
apizr plugins list --active --plugins-dir ./trusted-plugins --json
apizr plugins enable outerspace-apizr-mcp --version 0.4.0rc1 --plugins-dir ./trusted-plugins
```

`sync` uses installed uv offline, validates constraints and installs into separate
environments. It leaves the plugin inactive; the active list remains empty in a
new store until `enable`. Continue with the
[analysis MCP client setup](apizr-mcp-server.md), or the
[OCI](oci-service-plugin.md) and [Attest](attest-delivery-plugin.md) operation guides.
Activation is not a sandbox. External tools and credentials remain explicit
operation inputs, never profile contents.

Each plugin has its own dependency closure. Attest's Python dependency on
`outerspace-apizr-oci` is inside **Attest's environment**. It does not register or activate a
separate OCI installation. `delivery` explicitly selects both installations.

## Document contract and Python API

The [JSON schema](../specs/apizr-plugin-catalog-v1.schema.json) describes
`apizr.plugin-catalog/v1`. Unknown fields, duplicate JSON keys, invalid types,
unknown protocols, duplicate entries/profiles/selections and missing profile
references are rejected. The file is limited to 1 MiB, 128 entries and 32 profiles;
a profile selects at most 32 plugins, each with at most 127 dependency wheels.

Each entry reuses the existing manifest and locked wheel identity. It adds a
short description, compressed wheel byte sizes, an exact target (Python patch,
implementation, ABI, platform and machine), a declared core version/channel,
operation-specific external prerequisites and source repository/commit/status.
Optional publication references are inert metadata. Requirements use the existing
[locked requirements subset](local-extensions.md), not a second policy language.
Their canonical path is `requirements/PLUGIN-NAME.lock` relative to the supplied
wheelhouse. Wheel filenames are single portable basenames. Symlinks and special
files, including through parent paths, are refused.

Resolve retains verified bytes in a private snapshot and applies existing wheel,
expanded archive and aggregate size limits. It compares the generated lock with
the complete catalog identity; altered or substituted manifests/dependencies are
refused. The original wheelhouse must still pass `lock check` and `sync` afterwards.
No automatic version fallback, download, subprocess, plugin import, store access
or project mutation occurs during resolution.

```python
from pathlib import Path
from apizr.plugin_catalog import load_catalog, resolve_profile, select_entry

catalog = load_catalog(Path("catalog/catalogue.json"))
entry = select_entry(catalog, "outerspace-apizr-mcp", "0.4.0rc1")
result = resolve_profile(catalog, "mcp", Path("wheels"), Path("plugin-plan"))
assert result.installation == "not_performed"
```

`generate_entries(project, wheelhouse, descriptions=..., provenance=...,
prerequisites=...)` generates typed entries from declarations and real inspected
wheels. Place the original requirements at their canonical artifact paths before
calling it. `Catalog`, `Profile`, `Identity`, `Provenance` and `Prerequisite` are
available from `apizr.plugin_catalog.models`; `serialize` produces canonical JSON.
The proof driver `scripts/catalog_plugin_plan.py` is a worked generation example.

## Compatibility and qualification limits

The target is exact; export on the same Python/platform as the catalog and lock.
Static wheel tag admission supports pure Python, the current native ABI, CPython
stable ABI on non-free-threaded builds, macOS arm64/x86_64/universal2 and modern
`manylinux_x_y` on known glibc x86_64/aarch64 hosts. For universal2 Python builds,
macOS checks use the running OS and active CPU slice rather than the interpreter
build deployment minimum. Other tags fail closed. This
bounded check follows [PyPA's wheel tag specification](https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/)
and does not replace uv's dependency/platform checks at installation.

The declared core version is necessary but insufficient: use the
recorded source commit and its qualification evidence. Catalog metadata does not
certify publisher identity, dependency constraints, external-tool availability or
successful operation. CI qualifies MCP through its real SDK client and OCI/Attest
through their existing disposable Docker/HTTPS-registry proofs. No registry or
release is published by preparing a catalog.
