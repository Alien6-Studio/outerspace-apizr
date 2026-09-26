# Project plugin declarations and locks

!!! warning "Development 0.4 — not released"

    These commands belong to the development wheel built from this PR's source.
    They are not in the published **0.3.0** package. The new pages are in the PR
    until it is merged and the normal documentation deployment succeeds.

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
`plugins lock create/check` and `mcp serve`. Store precedence is explicit
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

Synchronization, updates, removal, an official catalog/profiles and authorization
per operation/destination remain commitments of the initial 0.4 plan. This change
delivers configuration and locking only.
