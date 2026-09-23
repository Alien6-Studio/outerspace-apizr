# Install and use extensions

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
apizr plugins install https://example.org/example_plugin-1.0.0-py3-none-any.whl \
  --sha256 EXPECTED_SHA256
apizr plugins list
apizr plugins list --json
apizr plugins enable example-plugin --version 1.0.0
apizr plugins list --active --json
apizr plugins run example-plugin describe --arguments arguments.json
apizr plugins disable example-plugin
```

The digest checks integrity of the exact wheel bytes, **not trust in its author**.
The installer snapshots the local wheel before invoking uv. Both Apizr and uv's
`--require-hashes` check those bytes; changing the original file afterward cannot
change what is installed. A hash calculated from an untrusted file does not make
that file trustworthy.

`--plugins-dir /absolute/user/directory` explicitly overrides storage on every
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

The local path stays entirely offline. Neither path enables an index, Python
download, source build, dependency resolution or installer fallback. uv receives
an isolated environment and explicit
`--offline`, `--no-config`, `--no-cache`, `--no-python-downloads`, `--no-index`,
`--no-deps`, `--no-build`, `--no-sources` and hash checking where applicable.
See the [uv command reference](https://docs.astral.sh/uv/reference/cli/) for those
backend switches. Parent `UV_*`, `PIP_*`, Python settings and credentials are not
forwarded. uv output is discarded; CLI diagnostics contain fixed failure codes.
A missing backend is detected before any filesystem modification.

This iteration rejects directories, non-HTTPS URLs, source archives, any `Requires-Dist`
entry (including conditional or extra dependencies), malformed/incompatible
manifests, startup `.pth`/`sitecustomize.py`/`usercustomize.py` files, and unsafe
archive paths or links. Native compatibility and `Requires-Python` are checked
by uv; an incompatible wheel is a failed installation, never an available record.
Wheels are limited to 64 MiB, expanded content to 256 MiB / 10,000 archive entries,
and individual metadata files to 64 KiB. The module must be a Python file or a
package with `__main__.py` in the wheel's site-packages root.

## HTTPS wheels

The expected SHA-256 is mandatory and its format is checked before any network
request. HTTPS acquisition downloads into a private temporary directory, checks
the digest, and hands those same bytes to the existing local installer. Its
manifest, protocol, package metadata and dependency checks still apply, and uv
remains offline. An installation stays inactive; existing activation choices are
never changed by downloading or installing another version.

Certificate chains and hostnames are verified using Python's default TLS trust
store (including explicitly configured `SSL_CERT_FILE` / `SSL_CERT_DIR`). There
is no insecure TLS option. At most five redirects are followed, including across
hosts, and every target must use HTTPS without embedded credentials. HTTP and
other schemes, URL user information, fragments, control characters and malformed
ports are refused. URLs must use ASCII encoding (percent-encoding for paths and
queries, IDNA for international hostnames). Invalid URLs never fall back to local
paths. Query parameters may be used, but diagnostics never echo the URL.

The initial URL must end in a safe wheel filename, such as
`example_plugin-1.0.0-py3-none-any.whl`; this name is checked against the package
metadata. Redirect filenames and `Content-Disposition` cannot choose a local
destination. Files are created exclusively in a private directory. Transfers
read at most 64 KiB at a time and enforce the existing 64 MiB wheel limit on
received bytes, even without `Content-Length`. Compressed HTTP content is refused;
the wheel's own ZIP compression is supported by the local validator.

Defaults are 5 seconds for connection/TLS handshake, 10 seconds per blocking
read and 60 seconds for the whole transfer across redirects. A supervised stdlib
worker makes the total deadline and cancellation effective even during DNS or
slow response headers. On timeout or Ctrl-C, the worker is killed and reaped
(up to 2 seconds for cleanup), closing its sockets; the temporary directory is
removed before returning. No installation record or activation is written until
the existing installer succeeds. As with local installs, abrupt host loss or
SIGKILL can leave unregistered temporary files. OS operations stuck in an
uninterruptible state remain outside the normal cleanup guarantee.

The client sends no inherited cookies, authentication, proxy credentials or
`.netrc` data. It ignores proxy environment variables and does not offer private
repository authentication. This is explicit user-directed network access, not
an SSRF boundary for untrusted URLs supplied by other users; private HTTPS hosts
are permitted. Trust in the author still requires an independent decision.

The Python API `install_from_source(source, sha256, *, directory=None, python=None)`
dispatches explicit paths or URLs. `install_from_url(url, sha256, *, directory=None,
python=None, limits=DownloadLimits(), cancel=None, ca_file=None)` exposes typed
timeouts, a `threading.Event` for transfer cancellation, and an optional explicitly
trusted CA file. It returns the existing `Installation`. Cancellation covers
acquisition; once installation begins, existing installer interruption rules
apply. `DownloadCancelled` and fixed `PluginError` codes such as
`download_timeout`, `download_tls_failed`, `download_incomplete`, `wheel_too_large`
or `hash_mismatch` contain no server messages or URL parameters. No download is
performed by `list`, `enable`, `disable` or `run`, and `apizr.toml` is not consulted.

The transfer uses the standard library's
[`HTTPSConnection`](https://docs.python.org/3/library/http.client.html#http.client.HTTPSConnection)
and [`create_default_context`](https://docs.python.org/3/library/ssl.html#ssl.create_default_context);
no new runtime dependency is required.

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
Pass `active=True` to filter it to the explicitly selected versions. These
functions do not print or exit the host. `PluginError` exposes a fixed message
such as `hash_mismatch`, `invalid_manifest`, `dependencies_not_supported`,
`installation_conflict`, `uv_not_found`, `uv_install_failed` or `uv_timeout`.
The CLI returns 2 on failure, 130 on keyboard interruption, and 0 on success.

`list --json` emits `apizr.installed-extensions/v1` with an `installations` array.
Records contain manifest fields plus `sha256`, `environment_id` and the absolute
`python` path. Listing is an inventory, not an interpreter health check: external
removal/upgrades of Python can invalidate an existing environment. No automatic
repair or download occurs. A corrupt local inventory fails closed.

## Explicit activation and invocation

Every installation starts inactive. `enable NAME --version VERSION` selects an
exact installed version without running it. Names use the same normalization as
the manifest. Repeating the same activation is idempotent; installing another
version leaves the selection unchanged. Switching requires another explicit
`enable` with the desired version. `disable NAME` is also idempotent.

`activations.json` is separate from `installations.json`. Its
`apizr.active-extensions/v1` document stores the selected installation records,
including name, version, SHA-256, environment ID, module, protocol and interpreter.
Updates use the existing store lock and atomic replacement. Before admitting a
call, Apizr checks that the selected record still matches the inventory and its
interpreter exists in the expected environment. Missing, inactive, inconsistent
or corrupt records fail closed, without repair. `list --active --json` validates
the bindings and emits the unchanged inventory format; it does not run plugins,
check interpreter health or contact the network.

The lock is released once an invocation is admitted. Disabling blocks later
admissions; an already admitted invocation may start or finish afterward. It does
not hold the lock for the plugin's execution or cancel an existing call.

`run` accepts a regular UTF-8 JSON file containing an object. Reads are bounded;
special files, duplicate keys, non-finite numbers and malformed JSON are refused.
It uses the recorded interpreter/module and the existing
[invocation runtime](extension-invocation.md), passing **an empty environment**.
Parent secrets are not forwarded. No plugin discovery, installation, download
or automatic `apizr.toml` loading takes place.

The CLI uses runtime defaults: a 10-second invocation deadline, 1 MiB request
and stdout limits, 64 KiB stderr limit and a 1-second cleanup deadline. The JSON
file itself is limited to 1 MiB; the complete encoded request must also fit the
request limit. These runtime deadlines begin after admission; acquiring the store
lock has its own 30-second limit. A successful structured protocol response goes
to stdout. Failures emit only fixed codes on stderr and return 2; Ctrl-C cleans
up through the runtime and returns 130. Plugin diagnostics are not echoed.

The Python API offers `enable_extension(name, version, *, directory=None)`,
`disable_extension(name, *, directory=None)` and
`run_extension(name, operation, arguments, *, directory=None, limits=Limits(),
cancel=None)`. The latter returns the existing `Response`, raises the existing
runtime errors, and accepts a `threading.Event` for cancellation. `read_arguments`
provides the same bounded JSON reader independently of the CLI. No operation
prints or exits Python. For example, after explicitly enabling the demo:

```python
from pathlib import Path
from apizr.extension_runtime import Limits
from apizr.local_plugins import run_extension

response = run_extension(
    "apizr-extension-probe",
    "describe",
    {"source_digest": "explicit-active-example"},
    directory=Path("/temporary/apizr-plugins"),
    limits=Limits(wall_time_ms=3000),
)
```

Activation is permission to use trusted code, **not a sandbox**. It does not
authenticate the author or continuously verify installed file contents. The
lower-level `invoke_extension` API remains an explicit caller-managed operation;
it does not consult the activation store.

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
printf '%s\n' '{"source_digest":"explicit-active-example"}' > arguments.json
# Refused: the installation is inactive.
apizr plugins run apizr-extension-probe describe --arguments arguments.json \
  --plugins-dir /temporary/apizr-plugins
apizr plugins enable apizr-extension-probe --version 0.0.0 \
  --plugins-dir /temporary/apizr-plugins
apizr plugins list --active --json --plugins-dir /temporary/apizr-plugins
apizr plugins run apizr-extension-probe describe --arguments arguments.json \
  --plugins-dir /temporary/apizr-plugins
apizr plugins disable apizr-extension-probe --plugins-dir /temporary/apizr-plugins
# Refused again after disabling.
apizr plugins run apizr-extension-probe describe --arguments arguments.json \
  --plugins-dir /temporary/apizr-plugins
```

The fixture's digest is calculated by the test after building its reviewed local
source. CI executes the CLI as `CORE_PYTHON -I -B -m apizr.cli` to exclude checkout
imports and bytecode writes in the measured core. Before/after inventories include
core file bytes, permissions, symlinks, additions/deletions and installed distributions.
The proof retains the original packaging/runtime checks, exercises idempotence,
and verifies both refusals and the successful activated call. While enabled, it
also copies and runs
[`invoke_active.py`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/examples/extension-probe/invoke_active.py)
outside the checkout, using the Python API example above.

The same workflow also starts a disposable localhost HTTPS server, generates its
test certificate with OpenSSL, and explicitly trusts that certificate via
`SSL_CERT_FILE` for one installed-core command. It downloads and installs the demo
into a fresh store, verifies that invocation is refused while inactive, then
enables and invokes it. The server is stopped before activation and invocation.
The final core snapshot covers both the local and HTTPS paths. No test disables
TLS verification, and no workstation Homebrew installation is changed.

For a wheel at a trusted HTTPS endpoint, the equivalent user commands are:

```sh
apizr plugins install https://example.org/apizr_extension_probe-0.0.0-py3-none-any.whl \
  --sha256 EXPECTED_SHA256 --plugins-dir /temporary/apizr-plugins
apizr plugins list --active --json --plugins-dir /temporary/apizr-plugins
# The new installation is inactive; enable it explicitly before run.
apizr plugins enable apizr-extension-probe --version 0.0.0 \
  --plugins-dir /temporary/apizr-plugins
apizr plugins run apizr-extension-probe describe --arguments arguments.json \
  --plugins-dir /temporary/apizr-plugins
```

[`examples/extension-probe/invoke_installed.py`](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/examples/extension-probe/invoke_installed.py)
is copied outside the checkout and run by that installed core:

```sh
CORE_PYTHON -I -B /temporary/invoke_installed.py /temporary/apizr-plugins
```

It explicitly selects the demonstration record and calls `invoke_extension` with
that record's interpreter and module. Listing itself does not invoke anything.
Run installation proofs only in disposable environments; do not update workstation
Homebrew dependencies to reproduce the CI job. No publication is performed.
