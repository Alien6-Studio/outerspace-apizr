# Install and list local extensions

Available in the development checkout; not yet part of published 0.3.0.
Install an explicitly trusted, dependency-free wheel into its own Python
virtual environment. Installation does not activate or invoke it, and project
configuration cannot install or load extensions. Historical `apizr.pipeline.v1`
plugins keep their existing behavior.

## Commands

With **uv already installed** and an expected SHA-256 obtained from a source you
trust:

```sh
apizr plugins install ./extension.whl --sha256 EXPECTED_SHA256
apizr plugins list
apizr plugins list --json
```

The digest checks integrity of the exact wheel bytes, **not trust in its author**.
The installer snapshots the local wheel before invoking uv. Both Apizr and uv's
`--require-hashes` check those bytes; changing the original file afterward cannot
change what is installed. A hash calculated from an untrusted file does not make
that file trustworthy.

`--plugins-dir /absolute/user/directory` explicitly overrides storage on either
command, particularly for disposable tests and CI. Defaults follow the packaging
ADR: `$XDG_DATA_HOME/apizr/plugins` (otherwise `~/.local/share/apizr/plugins`) on
Linux, and `~/Library/Application Support/apizr/plugins` on macOS. The store must
be user-owned, not writable by other users, and outside the core and the current
project (identified by an enclosing `.git` or `pyproject.toml`). An arbitrary
unmarked directory cannot be recognized as a project; choose a dedicated store.

Installation uses the running core's already installed interpreter to create a
new environment. `--python /absolute/path/to/python` explicitly selects another
installed interpreter. The interpreter symlink is not resolved before passing it
to uv, so an existing venv retains its identity. The new environment has no access
to the core's site-packages. Nothing is injected into uv tool, pipx or Homebrew.

No index, network access, Python download, source build, dependency resolution or
installer fallback is enabled. uv receives an isolated environment and explicit
`--offline`, `--no-config`, `--no-cache`, `--no-python-downloads`, `--no-index`,
`--no-deps`, `--no-build`, `--no-sources` and hash checking where applicable.
See the [uv command reference](https://docs.astral.sh/uv/reference/cli/) for those
backend switches. Parent `UV_*`, `PIP_*`, Python settings and credentials are not
forwarded. uv output is discarded; CLI diagnostics contain fixed failure codes.
A missing backend is detected before any filesystem modification.

This iteration rejects directories, URLs, source archives, any `Requires-Dist`
entry (including conditional or extra dependencies), malformed/incompatible
manifests, startup `.pth`/`sitecustomize.py`/`usercustomize.py` files, and unsafe
archive paths or links. Native compatibility and `Requires-Python` are checked
by uv; an incompatible wheel is a failed installation, never an available record.
Wheels are limited to 64 MiB, expanded content to 256 MiB / 10,000 archive entries,
and individual metadata files to 64 KiB. The module must be a Python file or a
package with `__main__.py` in the wheel's site-packages root.

## Declarative wheel manifest

A wheel contains exactly one root `apizr-extension.json`:

```json
{
  "schema": "apizr.extension-manifest/v1",
  "name": "apizr-extension-probe",
  "version": "0.0.0",
  "module": "apizr_extension_probe.runtime",
  "protocol": "apizr.extension/v1"
}
```

No plugin import is needed to read it. Fields and types are strict; unknown fields,
duplicate JSON keys, unknown schema/protocol versions and invalid module names
are rejected. `name` is the canonical distribution name (lowercase, runs of
hyphens/underscores/dots normalized to a hyphen). Name/version must match wheel
filename and distribution metadata. The manifest version is the package version;
the schema and invocation protocol have independent versions.

For Hatch, the demonstration includes the file with:

```toml
[tool.hatch.build.targets.wheel.force-include]
"apizr-extension.json" = "apizr-extension.json"
```

## Python operations and inventory

`apizr.local_plugins.install_extension(wheel: Path, sha256: str, *,
directory: Path | None = None, python: Path | None = None) -> Installation`
performs the operation. `list_extensions(*, directory: Path | None = None) ->
Inventory` reads local metadata only, without invoking uv or any interpreter.
Neither function prints or exits the host. `PluginError` exposes a fixed message
such as `hash_mismatch`, `invalid_manifest`, `dependencies_not_supported`,
`installation_conflict`, `uv_not_found`, `uv_install_failed` or `uv_timeout`.
The CLI returns 2 on failure, 130 on keyboard interruption, and 0 on success.

`list --json` emits `apizr.installed-extensions/v1` with an `installations` array.
Records contain manifest fields plus `sha256`, `environment_id` and the absolute
`python` path. Listing is an inventory, not an interpreter health check: external
removal/upgrades of Python can invalidate an existing environment. No automatic
repair or download occurs. A corrupt local inventory fails closed.

## Atomic visibility and interruption

A POSIX file lock serializes writers (30-second acquisition limit). Each install
gets a unique final `environments/ID/venv` path; the venv is never moved. uv commands
have a 120-second deadline each, with process-group cleanup and a bounded child
wait. A successful install is committed by an atomic replacement of
`installations.json`; readers see either complete inventory, without taking a
write lock. At most 1,000 records / 1 MiB of inventory are supported.

The same canonical name, version and digest is idempotent. Different bytes under
an existing name/version are refused. A different version gets another independent
environment, without activation, switching or an implicit upgrade.

Ordinary failures and Ctrl-C remove unpublished environments and preserve earlier
records. SIGKILL, machine loss or filesystem errors may leave unregistered files;
these do not appear in `list`. Cleanup does not delete a fully installed environment
whose record became visible just before an interruption. There is no garbage
collection or uninstall command in this iteration. Atomic visibility is not a
promise of durability across power loss or a broken filesystem.

This is **not a sandbox**: approved extensions, uv and Python have the user's
permissions. Storage is a local user trust boundary, not protection from a hostile
process running as the same user. Detached subprocesses and uninterruptible OS
operations have the limits documented for [extension invocation](extension-invocation.md).
Only POSIX Linux/macOS are supported.

## Installed demonstration

On disposable runners, the existing extension-packaging workflow builds real
wheels, installs the minimal core separately (uv tool or Homebrew), then uses
that **installed core outside the checkout** to run:

```sh
apizr plugins install ./apizr_extension_probe-0.0.0-py3-none-any.whl \
  --sha256 EXPECTED_SHA256 --plugins-dir /temporary/apizr-plugins
apizr plugins list --plugins-dir /temporary/apizr-plugins
apizr plugins list --json --plugins-dir /temporary/apizr-plugins
```

The fixture's digest is calculated by the test after building its reviewed local
source. CI executes the CLI as `CORE_PYTHON -I -B -m apizr.cli` to exclude checkout
imports and bytecode writes in the measured core. Before/after inventories include
core file bytes, permissions, symlinks, additions/deletions and installed distributions.
The proof retains the original packaging/runtime checks and exercises idempotence.

[`examples/extension-probe/invoke_installed.py`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/examples/extension-probe/invoke_installed.py)
is copied outside the checkout and run by that installed core:

```sh
CORE_PYTHON -I -B /temporary/invoke_installed.py /temporary/apizr-plugins
```

It explicitly selects the demonstration record and calls `invoke_extension` with
that record's interpreter and module. Listing itself does not invoke anything.
Run installation proofs only in disposable environments; do not update workstation
Homebrew dependencies to reproduce the CI job. No publication is performed.
