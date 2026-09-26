# Install and use extensions

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel) and record its source commit.

Install an explicitly trusted wheel into its own Python
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
download, source build or installer fallback. Dependency resolution is limited
to explicitly locked local wheels when both dependency options are supplied. uv receives
an isolated environment and explicit
`--offline`, `--no-config`, `--no-cache`, `--no-python-downloads`, `--no-index`,
`--no-deps`, `--no-build`, `--no-sources` and hash checking where applicable.
See the [uv command reference](https://docs.astral.sh/uv/reference/cli/) for those
backend switches. Parent `UV_*`, `PIP_*`, Python settings and credentials are not
forwarded. uv output is discarded; CLI diagnostics contain fixed failure codes.
A missing backend is detected before any filesystem modification.

Without `--requirements` and `--wheelhouse`, any `Requires-Dist` entry (including
conditional or extra dependencies) remains refused. Both paths reject directories,
non-HTTPS URLs, source archives, malformed/incompatible
manifests, startup `.pth`/`sitecustomize.py`/`usercustomize.py` files, and unsafe
archive paths or links. Native compatibility and `Requires-Python` are checked
by uv; an incompatible wheel is a failed installation, never an available record.
Wheels are limited to 64 MiB, expanded content to 256 MiB / 10,000 archive entries,
and individual metadata files to 64 KiB. The module must be a Python file or a
package with `__main__.py` in the wheel's site-packages root.

## Locked local dependencies

Supply both options together; the plugin may be a local wheel or an HTTPS URL:

```sh
apizr plugins install ./plugin-1.0.0-py3-none-any.whl --sha256 EXPECTED_SHA256 \
  --requirements requirements.lock --wheelhouse ./wheels
```

The accepted requirements subset is deliberately small: one `name==version`
with exactly one `--hash=sha256:HEX` per distribution, including the plugin and
**all transitive dependencies**. Blank lines, `#` comments and backslash line
continuations are supported. Names are normalized; duplicates are rejected.
Extras, markers, wildcard/range pins, multiple hashes, URLs, local paths,
editable installs, file inclusions and every other requirements option are
rejected. Prepare one lock/wheelhouse for the intended Python/platform target;
uv checks dependency constraints, wheel tags and `Requires-Python`.

```text
example-plugin==1.0.0 --hash=sha256:PLUGIN_SHA256
example-helper==2.0.0 --hash=sha256:HELPER_SHA256
example-leaf==3.0.0 --hash=sha256:LEAF_SHA256
```

Use real 64-character digests instead of these placeholders. The wheelhouse
must contain exactly one wheel for each locked dependency. Unlocked or ambiguous
dependency wheels are rejected. The plugin's optional wheelhouse copy is ignored:
its explicit source and `--sha256` determine the installed bytes. Other files are
ignored and never passed to uv. Dependency wheels do not need an Apizr manifest;
all wheels undergo the same archive and startup-file checks. Direct references
in wheel dependency metadata are also refused.

The lock is limited to 64 KiB and 128 distributions including the plugin.
Wheelhouse enumeration is bounded to 128 entries; selected wheels total at most
256 MiB compressed and 512 MiB expanded, in addition to the per-wheel limits.
Apizr copies validated bytes into a private snapshot. uv resolves only against
that snapshot with `--require-hashes`, `--no-index`, `--offline`, `--no-build`
and `--strict`; this path does **not** use `--no-deps`. Missing transitives,
conflicting versions and incompatible Python/platform constraints fail before
an installation becomes available. Validation does not import plugin code.

The recorded lock identity is SHA-256 of the original lock bytes (including
comments/whitespace); dependency records contain the exact installed versions
and wheel digests. Changing either the lock or dependencies for an existing
name/version raises `installation_conflict`. There are no implicit updates.
The existing activation remains unchanged, and a newly installed version starts
inactive. Files/distributions in the core environment remain untouched.

The Python operations `install_extension`, `install_from_source` and
`install_from_url` accept the same `requirements=Path(...)` and
`wheelhouse=Path(...)` keyword arguments. Their existing return types, errors,
HTTPS limits and interruption behavior are retained.

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
performed by `list`, `enable`, `disable`, `run` or `uninstall`, and `apizr.toml` is not consulted.

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
directory: Path | None = None, python: Path | None = None,
requirements: Path | None = None, wheelhouse: Path | None = None) -> Installation`
performs the operation. `list_extensions(*, directory: Path | None = None) ->
Inventory` reads local metadata only, without invoking uv or any interpreter.
Pass `active=True` to filter it to the explicitly selected versions. These
functions do not print or exit the host. `PluginError` exposes a fixed message
such as `hash_mismatch`, `invalid_manifest`, `dependencies_not_supported`,
`installation_conflict`, `uv_not_found`, `uv_install_failed` or `uv_timeout`.
The CLI returns 2 on failure, 130 on keyboard interruption, and 0 on success.

`list --json` emits `apizr.installed-extensions/v1` with an `installations` array.
Records contain manifest fields plus `sha256`, `environment_id` and the absolute
`python` path. New records also include `lock_sha256` (null for single-wheel
installs) and `dependencies` (name, version and wheel SHA-256). Existing records
without those fields remain readable. Listing is an inventory, not an interpreter health check: external
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

The same canonical name, version, digest and lock identity is idempotent. Different bytes under
an existing name/version are refused. A different version gets another independent
environment, without activation, switching or an implicit upgrade.

Ordinary failures and Ctrl-C remove unpublished environments and preserve earlier
records. SIGKILL, machine loss or filesystem errors may leave unregistered files;
these do not appear in `list`. Cleanup does not delete a fully installed environment
whose record became visible just before an interruption. There is no garbage
collection; use the explicit version removal described below. Atomic visibility is not a
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

### Example with transitive dependencies

The reviewed local fixture in `examples/extension-locked` contains three packages:
`apizr-locked-probe` imports `apizr-locked-helper`, which imports
`apizr-locked-leaf`. Neither dependency has a plugin manifest.
From the checkout, prepare these trusted example wheels and their lock:

```sh
uv run --locked python scripts/prepare_locked_extension.py \
  --wheelhouse /tmp/apizr-locked-example/wheels
```

This explicit **preparation** step builds the three example projects and may
fetch their build backend; plugin installation itself never builds or downloads
dependencies. The script prints the plugin wheel, SHA-256 and lock paths. For
other plugins, obtain trusted compatible wheels beforehand and write a lock
containing every exact version and its independently verified SHA-256.

Using a separately installed Apizr development wheel, run from outside the checkout:

```sh
apizr plugins install /tmp/apizr-locked-example/wheels/apizr_locked_probe-1.0.0-py3-none-any.whl \
  --sha256 PRINTED_SHA256 --requirements /tmp/apizr-locked-example/requirements.lock \
  --wheelhouse /tmp/apizr-locked-example/wheels --plugins-dir /tmp/apizr-locked-store
apizr plugins enable apizr-locked-probe --version 1.0.0 --plugins-dir /tmp/apizr-locked-store
printf '%s\n' '{}' > /tmp/apizr-locked-example/arguments.json
apizr plugins run apizr-locked-probe answer --arguments /tmp/apizr-locked-example/arguments.json \
  --plugins-dir /tmp/apizr-locked-store
```

The response contains `"result": {"answer": 42}`. The existing installed-wheel
proof executes this sequence on disposable uv/Homebrew runners and records
`locked_dependencies_verified`, the dependency inventory and invocation response.
Its before/after core file and distribution comparisons cover this sequence too:

```sh
uv run --locked python scripts/smoke_extension_packaging.py \
  --work-dir /tmp/apizr-locked-proof
```

## Portable project locks and local preferences

Development 0.4 adds [project declarations, explicit user preferences and portable artifact locks](project-plugin-locks.md). Use `plugins lock create/check` to validate artifacts and `plugins sync --project apizr.toml --lock apizr.plugins.lock.json --wheelhouse ./wheels --dry-run --json` to preview additive installation. Remove `--dry-run` to install the missing versions explicitly. `--user-config` selects local store preferences on all plugin commands and `mcp serve`; explicit `--plugins-dir` takes precedence. Neither project declarations nor locks activate anything. Synchronization keeps existing versions and activations; removal remains future work. See the linked page for partial results, resuming, cancellation and installed-wheel proofs.

## Controlled locked updates

Development **0.4 remains unreleased**. `plugins update` prepares one explicitly
locked version in a separate environment. It never modifies an existing
environment in place or removes an older version. There is no automatic version
selection, catalogue, dependency download or source build. A complete local
wheelhouse and an already installed Python are required; uv is needed only when
the target environment is missing.

```sh
apizr plugins update NAME --from-version INSTALLED_VERSION \
  --project /path/next/apizr.toml --lock /path/next/apizr.plugins.lock.json \
  --wheelhouse /path/wheels --dry-run --json
```

Remove `--dry-run` to prepare the target. Add `--activate` only when you also want
to select it. `--plugins-dir` overrides the explicitly selected `--user-config`
store, then the platform default. The project cannot choose the store or request
activation. There is no implicit user-file discovery. `--timeout-ms` retains the
sync default of 120000 ms and inclusive 1–600000 ms bounds; Python callers can
supply a cancellation Event.

The whole project/lock and artifact set must be coherent, but only NAME and its
closure are installed. The source version must already be registered. The target
comes exclusively from the project and lock. No version ordering is inferred,
so an explicitly requested older version is allowed. A target equal to the source
or already installed with the same complete identity is reused. Different hashes,
manifest module/protocol or requirements/dependency identity under the same
name/version are refused without replacement. Requirements retain their original
byte identity; no normalization or rewriting takes place.

Dry-run creates no absent store, changes no persistent state and starts neither
uv nor a plugin interpreter. `interpreter_verified: false` records the remaining
apply-time check. Apply retains the validated private snapshot used by sync,
installs through its offline backend and probes the registered target using the
same fixed, bounded `-I -S -B` standard-library program. It never imports the
plugin or project and does not run a business-operation health check. Structural
viability and Python target agreement do not prove functional compatibility with
every project or cryptographic integrity of every virtualenv file.

### Conditional activation and concurrent operators

Without `--activate`, even an inactive plugin or a third active version remains
exactly as selected. With `--activate`, the starting activation must match the
complete source binding or the already matching target. Inactive plugins must
first be selected with `enable`; a third selection is refused before installation.

Update captures the source and activation under the store lock, releases it while
preparing/probing the target, then reacquires it. It compares the complete source
and target records (including environment IDs) and the expected activation before
atomically writing the target selection. Other plugin activations are preserved.
A concurrent disable or different selection causes a refusal, not an override.
Identical concurrent requests can converge when the same verified target has
already been selected. Competing requests for different targets cannot both use
the same original active source. These are current-record comparisons, not a
history of intervening operator actions.

Installation and activation are separate steps, not a global transaction. An
installer failure preserves A and its activation. If B installs successfully but
the activation comparison fails, B remains installed and the current activation
is retained. Correct the explicit precondition if appropriate and rerun the same
command: the verified B is reused, including when uv is absent. Never rebuild or
replace artifacts under the same locked identity to obtain a successful retry.

An already admitted invocation or MCP session can finish on A after B is selected;
A and its dependencies are retained. New admissions use the activation they
observe. Explicit rollback is `plugins enable NAME --version OLD_VERSION`; update
never initiates rollback based on executing a plugin operation.

### Result and failure contract

The typed Python operation is independent of the CLI:

```python
from pathlib import Path
from threading import Event
from apizr.plugin_update import update_plugin

cancel = Event()
result = update_plugin(
    "apizr-update-probe",
    "1.0.0",
    Path("2.0.0/apizr.toml"),
    Path("2.0.0/apizr.plugins.lock.json"),
    Path("wheels"),
    directory=Path("plugins"),
    activate=True,
    timeout_ms=120000,
    cancel=cancel,
)
assert result.exit_code == 0, result.diagnostics
```

`--json` keeps stdout exclusively `apizr.plugin-update/v1`, even for recoverable
partial failure. The document includes:

- `mode`, `state`, `exit_code`, plugin/source version, full captured `source`
  installation, locked `target`, observed `target_installation`, `python_target`
  and `lock_sha256`. Installation records reuse the existing contract, including
  the local interpreter path and environment identity.
- `installation`: `not_attempted`, `planned`, `reused`, `installed`, `failed` or
  `unconfirmed`; `interpreter_verified` reports a completed target probe.
- `activation_requested`, distinct `activation` outcome, and the observed
  `active_before`/`active_after` records. A null activation with `before_known` or
  `after_known` true means inactive; false means it could not be established.
- Stable redacted `diagnostics`; never raw uv output or the parent environment.

`activation` distinguishes `not_requested`, `not_attempted`, `planned`, `changed`,
`unchanged`, `refused`, `observed_target` and `unconfirmed`. After interruption,
`observed_target` only reports the selection seen during reconciliation; it does
not convert that interrupted command into success or claim which writer selected
it. On success, `changed` records this call's atomic write; the separate final
observation must still agree with the requested target. No selection is reserved
against future operator actions after the command returns.

| State | Exit | Meaning |
| --- | --- | --- |
| `planned` | 0 | Simulation without blocking divergence; no mutation |
| `complete` | 0 | Target verified and, if requested, activation successful |
| `refused` | 1 or 2 | Before mutation: divergence/precondition (1) or operational/input error (2) |
| `partial` | 2 | Installation/activation work started but the full request failed |
| `interrupted` | 130 | Cancellation; observed published progress retained |
| `unconfirmed` | 2 or 130 | State/cleanup could not be confirmed; 130 retains user interruption |

The deadline spans preparation, bounded store waits, offline uv and the target
probe. Existing per-command and size limits from sync apply. Cleanup has its
separate two-second grace; reconciliation rereads published state under the lock
with a further two-second budget, including around atomic activation writes.
No successful environment is deleted on failure. Cancellation stops supervised
work, reaps the direct process and releases the lock. SIGKILL, loss of the machine,
detached descendants and noninterruptible OS operations retain the documented
limits: a final report and immediate cleanup cannot be guaranteed in those cases.

### Complete installed-wheel example

From the development checkout, use a fresh work directory outside it. Preparation
may download the core/build dependencies; update itself is strictly offline.
The trusted fixture uses the existing plugin → helper → leaf example, with
versions A/B that return 42/73 through different transitive dependencies.

```sh
work=$(mktemp -d)
uv build --wheel --out-dir "$work/dist"
uv venv --no-python-downloads --python python3 "$work/core"
uv pip install --python "$work/core/bin/python" "$work"/dist/outerspace_apizr-*.whl
python3 scripts/prepare_update_extensions.py --work-dir "$work/update"
core_python="$work/core/bin/python"
cd "$work/update"
"$core_python" -I -B -m apizr.cli plugins lock create --project 1.0.0/apizr.toml --wheelhouse wheels --output 1.0.0/apizr.plugins.lock.json --json
"$core_python" -I -B -m apizr.cli plugins lock create --project 2.0.0/apizr.toml --wheelhouse wheels --output 2.0.0/apizr.plugins.lock.json --json
"$core_python" -I -B -m apizr.cli plugins sync --project 1.0.0/apizr.toml --lock 1.0.0/apizr.plugins.lock.json --wheelhouse wheels --user-config user.toml --json
"$core_python" -I -B -m apizr.cli plugins enable apizr-update-probe --version 1.0.0 --user-config user.toml
"$core_python" -I -B -m apizr.cli plugins run apizr-update-probe answer --arguments arguments.json --user-config user.toml
"$core_python" -I -B -m apizr.cli plugins update apizr-update-probe --from-version 1.0.0 --project 2.0.0/apizr.toml --lock 2.0.0/apizr.plugins.lock.json --wheelhouse wheels --user-config user.toml --dry-run --activate --json
"$core_python" -I -B -m apizr.cli plugins update apizr-update-probe --from-version 1.0.0 --project 2.0.0/apizr.toml --lock 2.0.0/apizr.plugins.lock.json --wheelhouse wheels --user-config user.toml --json
```

The first invocation returns 42. Preparing B still leaves A active. The two locks
have different output paths: `lock create` refuses to overwrite a different file.
Do not rebuild wheels or edit original requirements after locking.

```sh
"$core_python" -I -B -m apizr.cli plugins update apizr-update-probe --from-version 1.0.0 --project 2.0.0/apizr.toml --lock 2.0.0/apizr.plugins.lock.json --wheelhouse wheels --user-config user.toml --activate --json
"$core_python" -I -B -m apizr.cli plugins run apizr-update-probe answer --arguments arguments.json --user-config user.toml
```

B now returns 73. Repeat the update command: both installation and activation are
reused. To return explicitly to A without reinstallation:

```sh
"$core_python" -I -B -m apizr.cli plugins enable apizr-update-probe --version 1.0.0 --user-config user.toml
"$core_python" -I -B -m apizr.cli plugins run apizr-update-probe answer --arguments arguments.json --user-config user.toml
```

The result is again 42. After an activation conflict, inspect `plugins list
--active --json --user-config user.toml` and respect the current operator choice.
If you intentionally restore A with that explicit enable command, rerunning
update reuses B and attempts the conditional transition again.

The existing packaging workflow runs these operations from installed wheels on
Linux 3.11–3.14, macOS 3.11/3.14 and disposable Homebrew. It retains
`update-evidence.json`, `backend-network.jsonl`, `update-summary.json` and
`core-evidence.json`: dry-run equality, real uv failure/retry, prepare-only behavior,
transition/repetition with uv absent, explicit rollback, original-environment and
core file/distribution equality. OS network isolation covers Python and uv children.
Concurrent activation races, interruption reconciliation and in-flight calls are
also covered by explicitly synchronized tests. No Homebrew changes are needed on
the developer machine. Catalogue and automatic selection/download remain separate work; `--activate` is not a general permission engine.

## Remove one unused version

`disable` blocks future admissions; it does not stop an already admitted call or
MCP session. `uninstall` removes one exact version only after it is inactive and
no protected user remains. It never disables a plugin, kills its users, launches
an interpreter, contacts the network or invokes uv. There is no `--force` option.

For a plugin whose versions `1.0.0` and `2.0.0` are already installed, first select
and test the version you intend to retain, then preview and remove the old one:

```sh
apizr plugins enable my-plugin --version 2.0.0 --plugins-dir /absolute/plugin-store
apizr plugins uninstall my-plugin --version 1.0.0 --dry-run --json --plugins-dir /absolute/plugin-store
apizr plugins uninstall my-plugin --version 1.0.0 --json --plugins-dir /absolute/plugin-store
apizr plugins uninstall my-plugin --version 1.0.0 --json --plugins-dir /absolute/plugin-store
```

Replace `my-plugin` and the store with your installed plugin's actual name and
location. The preview reports `planned`; successful removal reports `complete`;
the repeated removal reports `absent`. To remove the active version instead,
explicitly run `plugins disable my-plugin`, close its sessions and wait for its
calls to finish. An ongoing use reports `busy` without terminating anything.
`--user-config` remains explicit, and `--plugins-dir` overrides its store setting.

### Usage protection and migration

Apizr coordinates admission and removal under the store lock. A separate shared
lock belongs to each installed generation; the global store lock is released
before an invocation or session. The usage descriptor survives the MCP launcher's
`execve` and is passed to extension processes and interpreter probes. Removal
checks an exclusive usage lock without waiting for users to exit. Lock files
remain as small, stable metadata after removal to prevent lock-identity races.

This covers calls and sessions admitted by this implementation. **Before first
using uninstall after upgrading**, stop sessions opened by older Apizr launchers
and processes launched directly with a plugin interpreter. Restart managed
sessions with the upgraded launcher. Apizr cannot universally detect these
unprotected processes. Trusted plugins must not deliberately close the inherited
usage descriptor. These locks coordinate cooperating local processes; they are
not a sandbox or a defense against a user who can rewrite the store itself.

A supervisor cleanup failure leaves a conservative `plugin_usage_unconfirmed`
guard. Removal is refused until the actual process/store state has been reviewed;
there is no automatic repair or assumption that the process has stopped.

### Interruption and exact cleanup

Removal writes a persistent cleanup intent containing the full installation
record and the environment directory identity. It then retires the inventory
record and erases that generation through directory descriptors. Internal
symlinks are unlinked, never followed; the shared Python used by a virtualenv is
not deleted. A redirected environment or inconsistent record is refused.

**Inventory retirement and file deletion are separate steps, not an atomic
transaction.** A pending generation cannot be enabled, invoked or reused by
install/sync/update, including after interruption between those steps. Rerun the
same `uninstall NAME --version VERSION` to resume. It refuses a changed generation
rather than deleting a new installation with the same name/version. Other plugins,
active versions, project declarations and locks are untouched. A later `sync`
can reinstall a removed version that remains declared in the project lock.

`--timeout-ms` bounds cooperative lock waiting and traversal (default 30000,
range 1–600000). One attempt traverses at most 100000 entries and 64 directory
levels; a limit leaves cleanup pending. A failure may use up to two additional
seconds to observe committed state. An OS filesystem call itself may block;
these are not hard real-time or filesystem quota guarantees.

`--json` returns `apizr.plugin-uninstall/v1`: `mode`, `state`, `exit_code`,
`plugin`, `version`, the exact `target`, `inventory_removed`,
`environment_removed`, `cleanup_pending`, `effects` and fixed-code `diagnostics`.
Preview effects describe intended changes; apply effects describe observed ones.

| State | Meaning | Exit |
| --- | --- | --- |
| `planned` | Preview allowed; no removal performed | 0 |
| `complete` | Record retired, environment removed, intent cleared | 0 |
| `absent` | No matching installation or pending cleanup | 0 |
| `active` / `busy` | Explicit disable or end of current use required | 1 |
| `refused` | Invalid input, identity/state mismatch or unavailable storage | 2 |
| `incomplete` | Cleanup did not finish; inspect effects and retry | 2 |
| `interrupted` | Cancellation; inspect persisted progress | 130 |
| `unconfirmed` | Process cleanup or final store state cannot be established | 2, or 130 after cancellation |

The typed API performs the same operation without printing or exiting:

```python
from pathlib import Path
from threading import Event
from apizr.local_plugins import uninstall_extension

cancel = Event()  # Another thread can set this to cancel cooperatively.
result = uninstall_extension(
    "my-plugin",
    "1.0.0",
    directory=Path("/absolute/plugin-store"),
    dry_run=True,
    timeout_ms=30000,
    cancel=cancel,
)
print(result.model_dump_json())
```

The installed-wheel update proof above also exercises A → update to B → select B
→ remove A → invoke B → repeat removal, with OS network denial and before/after
core inventories. The installed MCP proof uses a real SDK session: disable,
refuse removal while connected, complete another call, close, then remove.
Homebrew installation qualification runs only on disposable CI runners.
