# Project plugin declarations and locks

!!! warning "Development 0.4 — not released"

    These commands belong to development wheels for **0.4**.
    They are not in the published **0.3.0** package.

## Four separate kinds of state

| State | Content | Version with the project? |
| --- | --- | --- |
| `apizr.toml` | Requested plugin identities and requirements paths | Yes |
| `apizr.plugins.lock.json` | Verified wheel names, hashes, manifests, per-plugin dependency closures and target | Yes, together with referenced requirements |
| Installation inventory | Local environment identity, interpreter and installed distributions | No |
| Explicit `user.toml` | Operator's local plugin store preference | Usually no; keep local paths outside the project |

Nothing in a project or lock installs, activates or executes a plugin. A wheel
hash proves integrity, not author trust or execution permission. The user file
is a preference file, **not an authorization engine**. The repository cannot
supply an operator configuration path, store, module, interpreter, command,
automatic activation, destination permission, credentials or trust rules.
Unknown fields are refused.

## Declare exact artifacts

The existing `apizr.project/v1` gains an optional `[[plugins]]` array. Existing
files without it retain their behavior. For example, the preparation below
produces this file with the actual wheel SHA-256 in place of `WHEEL_SHA256`:

```toml
schema_version = "apizr.project/v1"

[[plugins]]
name = "apizr-locked-probe"
version = "1.0.0"
sha256 = "WHEEL_SHA256"
requirements = "requirements.lock"
```

Names must already be canonical (lowercase with hyphens); duplicate names,
including noncanonical spellings such as `Apizr_Locked_Probe`, are refused.
Versions are exact normalized numeric releases, optionally with an epoch,
`a`/`b`/`rc`, `.post`, `.dev` or local suffix. Wildcards and ranges are refused.
Hashes are lowercase SHA-256. Omit `requirements` only for a dependency-free
plugin. Otherwise use the [existing requirements subset](local-extensions.md#locked-local-dependencies):
exact pins and SHA-256, with comments and backslash continuations; no options,
includes, markers, extras, direct URLs, paths or editable installs.

Requirements paths are portable, relative to the project file, contained in
its directory tree, with no `..`, absolute paths or symlink traversal. Loading
`apizr.toml` only validates the declaration; it does not read these files or wheels.
The analysis root and policy rules are unchanged.

The operator may explicitly select:

```toml
schema_version = "apizr.user/v1"
plugins_dir = "locked-plugins"
```

`--user-config user.toml` works on `plugins install/list/enable/disable/run`,
`plugins lock create/check`, `plugins sync` and `mcp serve`. Store precedence is explicit
`--plugins-dir`, then the selected user file, then the existing platform default.
Relative paths in the user file resolve against that file; relative CLI paths
resolve against CWD. An explicitly chosen user file is validated even when its
store is overridden. No automatic discovery, `.env` loading, variable expansion
or secret interpolation occurs. Create/check only consult the store with
`check --installed`.

## Complete installed-wheel example

Use an already installed Python 3.11–3.14 and uv on macOS/Linux. From the chosen
development checkout, prepare a minimal core outside the checkout and build the
existing **trusted** plugin → helper → leaf fixture. This explicit preparation
may download core/build dependencies; create/check never do.

```sh
work=$(mktemp -d)
uv build --wheel --out-dir "$work/dist"
uv venv --no-python-downloads --python python3 "$work/core"
uv pip install --python "$work/core/bin/python" "$work"/dist/outerspace_apizr-*.whl
python3 scripts/prepare_locked_extension.py --wheelhouse "$work/locked-wheels"
python3 examples/project-plugins/prepare.py "$work"
core_python="$work/core/bin/python"
cd "$work"
```

The preparation writes exact hashes of all three wheels to `requirements.lock`:

```text
apizr-locked-leaf==1.0.0 --hash=sha256:LEAF_SHA256
apizr-locked-helper==1.0.0 --hash=sha256:HELPER_SHA256
apizr-locked-probe==1.0.0 --hash=sha256:PLUGIN_SHA256
```

Those uppercase digest labels explain the format; the preparation script replaces
all of them with real 64-character digests. Do not rebuild between checking and
installing. These exact commands are also exercised by the installed-wheel proof:

<!-- smoke:project-plugin-lock -->
```sh
"$core_python" -I -B -m apizr.cli plugins lock create --project "$work/apizr.toml" --wheelhouse "$work/locked-wheels" --output "$work/apizr.plugins.lock.json" --json
"$core_python" -I -B -m apizr.cli plugins lock check --project "$work/apizr.toml" --lock "$work/apizr.plugins.lock.json" --wheelhouse "$work/locked-wheels" --json
plugin_sha=$("$core_python" -I -B -c 'import hashlib,sys; from pathlib import Path; print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())' "$work/locked-wheels/apizr_locked_probe-1.0.0-py3-none-any.whl")
"$core_python" -I -B -m apizr.cli plugins install "$work/locked-wheels/apizr_locked_probe-1.0.0-py3-none-any.whl" --sha256 "$plugin_sha" --requirements "$work/requirements.lock" --wheelhouse "$work/locked-wheels" --user-config "$work/user.toml"
"$core_python" -I -B -m apizr.cli plugins lock check --project "$work/apizr.toml" --lock "$work/apizr.plugins.lock.json" --wheelhouse "$work/locked-wheels" --installed --user-config "$work/user.toml" --json
"$core_python" -I -B -m apizr.cli plugins list --active --user-config "$work/user.toml" --json
```
<!-- /smoke:project-plugin-lock -->

The final inventory is empty: installation remains inactive. Only an explicit
`plugins enable apizr-locked-probe --version 1.0.0 --user-config "$work/user.toml"`
activates it. The existing installer still performs its offline uv resolution and
installation checks; `lock create` is not an installer or a dependency resolver.

To reproduce all assertions, including subsequent activation/invocation, core
file/distribution equality and protocol refusals, run from the checkout:

```sh
python3 scripts/smoke_extension_packaging.py --work-dir "$(mktemp -d)/proof"
```

Its `evidence.json` retains the generated lock and create/check results. A [generated example](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/examples/project-plugins/apizr.plugins.lock.example.json) is retained in the source tree; its hashes and target describe that particular preparation, not new builds. Linux
Python 3.11–3.14 and macOS 3.11/3.14 runners also exercise this proof. Homebrew
installation qualification stays on disposable runners.

## Lock contract and target

`apizr.project-plugins/v1` has these fields:

| Field | Meaning |
| --- | --- |
| `schema_version` | Exact document version |
| `target` | Producer's Python implementation, full version, platform, machine and ABI; no executable path |
| `plugins[].manifest` | Existing verified `apizr.extension-manifest/v1`, including entry module and extension protocol |
| `plugins[].wheel` | Canonical name, exact version, SHA-256 and portable filename |
| `plugins[].dependencies` | Separately sorted closure of locked wheels for this plugin |
| `plugins[].requirements` | Project-relative path and `source_sha256` of original requirements bytes, or null |

`create` exports compact JSON with sorted keys, sorted plugins/dependencies and a
trailing newline. There are no timestamps, random IDs or machine paths. Reordering
wheelhouse entries or moving the same project does not change those bytes on the
same target. The result's `lock_sha256` hashes the **whole exported file**.
Requirements comments, line endings and ordering remain part of `source_sha256`;
changing only a comment therefore makes `check` report drift. No normalization
silently replaces that identity. A requirements path must travel with the project.

A lock is **target-specific**, even for pure Python wheels. Check refuses a target
different from the running interpreter's full target record. Static tag admission
is conservative: matching `py3`/`pyXY` (or CPython `cpXY`), `none`/current CPython
ABI, and `any`/the exact normalized current platform tag. Portable binary tags
such as manylinux, abi3 or a different macOS deployment target can be reported as
`wheel_target_not_verifiable`; no compatibility claim is made for them in this
iteration. Python package constraints and `Requires-Python` are finally evaluated
by the existing uv installer, not reimplemented here. A valid lock proves document
coherence and artifact integrity, **not that installation will succeed**.

Two plugins may lock different versions of the same dependency. The global
wheelhouse may contain both closures; each is selected by exact identity, then
verified against its declared hash and archive metadata. Multiple candidates for
one name/version are ambiguous even if one hash matches. Unrelated regular wheels
are not offered to the installer or included in the lock.

## Diagnostics, codes and Python API

Create/check emit `apizr.plugin-lock-result/v1`: `valid`, `lock_sha256`, `target`,
structured `diagnostics` (code, plugin, distribution) and optional `installed`
records (`name`, `matches`, `active`). `--json` keeps stdout exclusively JSON.
Malformed/unreadable input uses exit **2**, artifact/project/target/inventory drift
uses **1**, success uses **0**, interruption uses **130**. Command errors are
redacted on stderr; filenames and raw parser/installer diagnostics are not echoed.

Examples of divergence: `missing_wheel`, `ambiguous_wheel`, `hash_mismatch`,
`plugin_requirements_mismatch`, `project_artifacts_changed`, `target_mismatch`,
`installation_missing`, `installation_mismatch`. Invalid documents yield
`invalid_project`, `invalid_requirements` or `invalid_project_lock`. Unreadable files are distinguished as `project_unreadable`, `requirements_unreadable` or `lock_unreadable` (also exit 2).

`check --installed` compares name/version, main hash, manifest module/protocol,
requirements source hash and dependency versions/hashes with local records. It
reports activation separately. It neither requires activation nor audits all
virtualenv files cryptographically, checks interpreter viability or repairs state.
Reading the activation record uses the existing installation lock for a consistent
activation snapshot. No store or activation write occurs.

```python
from pathlib import Path
from apizr.plugin_lock import create_lock, check_lock

created = create_lock(
    Path("apizr.toml"), Path("wheels"), Path("apizr.plugins.lock.json")
)
checked = check_lock(
    Path("apizr.toml"), Path("apizr.plugins.lock.json"), Path("wheels")
)
assert created.valid and checked.valid
```

The typed API returns `Result`; malformed/unreadable input raises `LockError`
with a redacted code. Config loaders are `apizr.project.load_project` and
`apizr.user_config.load_user_config`, independent of CLI presentation.

## Bounds and publication safety

Project/user TOML: 64 KiB each; at most 32 plugins. Requirements retain their
64 KiB/128-distribution bounds. Lock JSON: 1 MiB. Wheelhouse enumeration: at most
512 entries, including non-wheels. Each wheel retains the existing 64 MiB compressed,
256 MiB expanded, 10,000-entry and 64 KiB metadata bounds. Selected wheels total at
most 256 MiB compressed; inspected closures total at most 512 MiB expanded (shared
wheels count again across closures for this bound). Archive traversal, startup
files and metadata checks are reused unchanged.

Inputs must be regular files; symlink traversal and special files are refused.
Standard macOS `/tmp` and `/var` aliases are resolved before descriptor-relative
traversal. Artifact validation uses retained private copies, so a later source
change cannot substitute bytes in the produced lock. Check always rereads current
artifacts. Output is published atomically without replacement: identical content
is idempotent, different existing content yields `output_conflict`. Parent output
directories must already exist. Interruption leaves no partially published lock.

Removal, an official catalog/profiles and authorization per
operation/destination remain commitments of the initial 0.4 plan. Synchronization
is additive; it does not deliver those separate features.

## Synchronize missing installations

`plugins sync` is an explicit, offline installation request. All three input paths
are required; no project, lock or wheelhouse is discovered automatically. The
wheelhouse must already contain every locked wheel. There is no remote cache or
catalogue lookup. Store selection keeps the precedence described above.

```sh
apizr plugins sync --project /path/project/apizr.toml \
  --lock /path/project/apizr.plugins.lock.json --wheelhouse /path/wheels \
  --dry-run --json
apizr plugins sync --project /path/project/apizr.toml \
  --lock /path/project/apizr.plugins.lock.json --wheelhouse /path/wheels \
  --timeout-ms 120000 --json
```

Simulation validates the artifacts and compares full installation identities. It
runs neither uv nor any plugin interpreter, creates no absent store and changes
no persistent state. `interpreter_verified: false` explicitly records that no
interpreter probe was performed. The later application repeats validation; a
previous preview does not reserve artifacts or store state.

Apply reuses the existing installer, which offers only each plugin's exact
closure to offline uv. Already present identities are reused without requiring
uv. Missing versions require an already installed uv and the current Python;
there is no Python download, source build or index. Existing versions and foreign
plugins are preserved. An identity conflict under the same name/version is
refused before any installation. Full identity includes module/protocol, main
wheel digest, **original** requirements digest and dependency versions/digests.
New versions remain inactive, including when an older version is active.

Apply probes each reused interpreter before starting installations and verifies
all final records/interpreters before success. The fixed, bounded probe runs with
`-I -S -B`, an empty environment and only the standard library; it imports no
plugin or project code. A missing or mismatched interpreter is refused without
repair. These checks are not a cryptographic audit of every virtualenv file.

### Retained inputs and per-plugin progress

Preparation retains the validated original lock, requirements and wheel bytes
in a private temporary snapshot. Per-plugin wheel selections are hardlinks to
those private copies, never to the input files. Changing originals after
preparation cannot replace installed bytes. Each installer additionally verifies
its private copy. Two plugins can use different versions of a common dependency.
Static validation does not resolve dependency constraints: uv can still refuse
an inconsistent closure during application.

Retained input storage is bounded by 256 MiB of selected wheel bytes, 32 × 64 KiB
of original requirements, and 1 MiB of lock JSON. Closures reuse those bytes;
the sequential installer can additionally copy one closure (up to 256 MiB) into
its scratch area. Existing per-wheel and expanded-closure bounds still apply.
These are input/archive bounds, not a filesystem quota on uv metadata, filesystem
block allocation or the final installed environments. Temporary snapshots are
removed on normal success, refusal and handled interruption.

Each environment is built at its final location and published atomically under
the existing store lock. There is **no transaction across plugins**. If A succeeds
and B fails, A remains available, B is not falsely published, and later plugins
are not started. Rerun the same command with the same artifacts to reuse A and
resume B. An interruption close to publication triggers a bounded inventory
reread; published environments are retained. If state cannot be established,
the result says `unconfirmed`, not rolled back. Concurrent identical syncs
converge through the installer's existing identity check under the store lock.
`action` records the initial plan: an `install` can find that another writer has
already published the same identity; `installed` means its presence was confirmed.
No sync operation writes activations.

### Results, deadlines and Python API

`--json` emits `apizr.plugin-sync/v1` on stdout, including recoverable partial
failures. Fields are `mode`, `state`, `exit_code`, `lock_sha256`, `target`, `plugins`
and redacted `diagnostics`. Each plugin has `name`, `version`, planned `action`
(`install`, `reuse`, `refuse`), `status`, separate `active` and
`interpreter_verified`. Unknown activation is null. A `planned` status is not an
installation. Final statuses include `installed`, `reused`, `refused`, `failed`,
`not_attempted` and `unconfirmed`. Operational stderr contains only stable codes;
raw uv output and inherited secrets are not returned.

| State | Meaning | Exit |
| --- | --- | --- |
| `planned` | Valid simulation, no interpreter verification | 0 |
| `complete` | All required records and interpreters verified | 0 |
| `refused` | Before installation: content/identity drift, or input/operational error | 1 for drift, 2 for operational errors |
| `partial` | Application did not finish; published progress retained | 2 |
| `interrupted` | User cancellation; progress reconciled where possible | 130 |
| `unconfirmed` | Cleanup or final inventory state could not be confirmed | 2, or 130 after user cancellation |

`--timeout-ms` is a total cooperative deadline: default 120000 ms, allowed
1–600000 ms. It includes validation, lock waiting, uv and probes. Store acquisition
also keeps its 30-second cap; each uv command its 120-second cap and each probe its
10-second cap, always shortened by the remaining total time. Supervised process
cleanup has a separate two-second grace; failure reconciliation permits a further
two seconds. Cancellation stops/reaps the process group and releases locks rather
than merely cancelling a waiting thread. Detached descendants retain the runtime's
documented cleanup limitation. Blocking filesystem calls cannot be preempted;
SIGKILL, machine loss or uninterruptible OS operations cannot guarantee timely
cleanup or a final report. No automatic repair or deletion is attempted on restart.

```python
from pathlib import Path
from threading import Event
from apizr.plugin_sync import sync_plugins

cancel = Event()  # Another thread may call cancel.set().
result = sync_plugins(
    Path("apizr.toml"),
    Path("apizr.plugins.lock.json"),
    Path("wheels"),
    directory=Path("plugins"),
    timeout_ms=120000,
    cancel=cancel,
)
assert result.exit_code == 0, result.diagnostics
```

### Installed-wheel proof with two closures

Extend the minimal-core preparation above from the checkout:

```sh
python3 scripts/prepare_sync_extensions.py --work-dir "$work/sync"
"$core_python" -I -B -m apizr.cli plugins lock create --project "$work/sync/apizr.toml" --wheelhouse "$work/sync/wheels" --output "$work/sync/apizr.plugins.lock.json" --json
"$core_python" -I -B -m apizr.cli plugins sync --project "$work/sync/apizr.toml" --lock "$work/sync/apizr.plugins.lock.json" --wheelhouse "$work/sync/wheels" --user-config "$work/sync/user.toml" --dry-run --json
"$core_python" -I -B -m apizr.cli plugins sync --project "$work/sync/apizr.toml" --lock "$work/sync/apizr.plugins.lock.json" --wheelhouse "$work/sync/wheels" --user-config "$work/sync/user.toml" --json
"$core_python" -I -B -m apizr.cli plugins lock check --project "$work/sync/apizr.toml" --lock "$work/sync/apizr.plugins.lock.json" --wheelhouse "$work/sync/wheels" --installed --user-config "$work/sync/user.toml" --json
```

Run sync again to observe `reused` for both. `plugins list --active --user-config
"$work/sync/user.toml" --json` stays empty until explicit activation. Then:

```sh
"$core_python" -I -B -m apizr.cli plugins enable apizr-sync-a --version 1.0.0 --user-config "$work/sync/user.toml"
"$core_python" -I -B -m apizr.cli plugins run apizr-sync-a answer --arguments "$work/sync/arguments.json" --user-config "$work/sync/user.toml"
```

Repeat enable/run for `apizr-sync-b`: A returns 42 and B returns 73 through their
different helper/leaf versions. All these commands are exercised by
`scripts/smoke_plugin_sync.py` against the installed core. It additionally forces
a real uv refusal for B, then resumes without changing wheels or requirements.
It compares core files/distributions and preserves JSON evidence per command.

The existing packaging proof prepares these six wheels once. On disposable
Linux/macOS runners, `scripts/run_plugin_sync_proof.py WORK` runs the installed
proof under a Linux network namespace or macOS sandbox with networking denied.
The restriction is inherited by uv children, not just Python socket calls.
Every backend invocation verifies network denial before executing real uv.
The existing uv and Homebrew qualification remains in place; no developer-machine
Homebrew updates are needed. `sync-evidence.json`, `backend-network.jsonl` and
`sync-summary.json` retain partial/resume, idempotence and core-integrity results.


## Prepare a controlled update

Use a new project declaration and original requirements for the target version,
then `plugins lock create --output apizr.plugins.next.lock.json`. Existing different
lock files are never overwritten: choose a new output filename instead of changing
that protection. Neither create nor update rewrites the project or requirements.

[`plugins update NAME --from-version VERSION`](local-extensions.md#controlled-locked-updates)
validates the whole supplied project/lock, but installs only NAME and its own
closure. Other missing project plugins stay missing. The target comes exclusively
from this lock; there is no latest-version selection or version-order comparison.
An explicitly chosen lower version is also a valid transition.

By default, update only prepares the target; activation is unchanged. With
`--activate`, the initially active installation must be the requested source or
the already conforming target. A conditional atomic comparison protects operator
changes made during installation. See the linked complete installed-wheel example
for simulation, retry, activation and an explicit return to the retained source.
