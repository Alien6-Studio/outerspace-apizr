---
title: Prepare a verified temporary plugin profile
description: Select compatible prebuilt wheels, verify resolver-admitted hashes and install the MCP plugin in an explicit temporary profile.
---

# Prepare a verified temporary plugin profile

`apizr plugins prepare` prepares wheels and a strict installer lock for an
explicit interpreter. It installs nothing and leaves activation to `plugins enable`.
This command is available in the **0.4.5 development line**; published 0.4.4 does
not contain it.

Use a build containing this command with the **`[preparation]` extra**, which
provides PyPA's wheel compatibility rules. For example, install the verified core
candidate into your existing tool environment with
`uv tool install '/absolute/path/outerspace_apizr-0.4.4-py3-none-any.whl[preparation]'`.
The minimal core still requires only Pydantic. Preparation also requires **uv
0.12.x**; `--uv /absolute/path/to/uv` selects a specific executable, whose version
is recorded in the result. Qualification uses uv 0.12.0.

## Prepare, install, activate, serve

Set `python` to an **absolute path** to the already installed CPython interpreter
that will run the plugin. Set `project` and `authority` to your project file and
reviewed [operator policy](operator-policy.md). Then use a temporary workspace:

```sh
python=/absolute/path/to/python3.14
project=/absolute/project/apizr.toml
authority=/absolute/operator.json
tmp=$(mktemp -d)
tmp=$(cd "$tmp" && pwd -P)

apizr plugins prepare outerspace-apizr-mcp --version 0.4.4 \
  --python "$python" --platform native \
  --index-url https://pypi.org/simple --output-dir "$tmp/prepared" --json

plugin_sha=$(awk '$1 == "outerspace-apizr-mcp==0.4.4" {sub("--hash=sha256:", "", $2); print $2}' \
  "$tmp/prepared/requirements.lock")
apizr plugins install "$tmp/prepared/wheelhouse/outerspace_apizr_mcp-0.4.4-py3-none-any.whl" \
  --sha256 "$plugin_sha" --python "$python" \
  --requirements "$tmp/prepared/requirements.lock" \
  --wheelhouse "$tmp/prepared/wheelhouse" --plugins-dir "$tmp/prepared/profile"
apizr plugins enable outerspace-apizr-mcp --version 0.4.4 \
  --plugins-dir "$tmp/prepared/profile"
apizr mcp serve --project "$project" --operator-policy "$authority" \
  --plugins-dir "$tmp/prepared/profile"
```

Run these commands in order, stopping on a refusal. The `awk` command reads the
plugin's already verified hash; you never rewrite resolver hashes manually.
Preparation, installation and activation remain separate review points. This
example downloads the published plugin; contributor qualification instead uses
core and plugin wheels built from the same recorded development commit.

The prepared directory contains:

```text
prepared/
├── wheelhouse/          exactly one verified wheel per distribution
├── requirements.lock   exact pins, one admitted SHA-256 per wheel
├── preparation.json    target, plugin, artifact identities and relative paths
└── profile/            empty until explicitly installed into
```

Keep this directory for offline reuse or remove this exact temporary workspace
after stopping its MCP server. All installation/activation commands above use
`--plugins-dir`; they do not change your normal plugin store or another profile.
See the [MCP server guide](apizr-mcp-server.md) for client configuration and calls.

## Existing wheels and multi-hash locks

For a reviewed local wheelhouse, replace `--index-url` with
`--wheelhouse /absolute/candidate-wheels`. With no index option the entire
preparation stays offline. Local sdists are ignored and cannot run a build.

To retain the admitted hashes from an existing `uv pip compile --generate-hashes`
lock, also pass `--requirements /absolute/resolver.lock`. Exact pins can contain
multiple SHA-256 hashes with uv-style line continuation and comments. Unpinned
requirements, editable installs, URLs, nested files, markers, extras, duplicate
distributions and unknown options are refused. The selected wheel's **actual
bytes** must match an admitted hash. Additional unresolved or unused pins cannot
silently become an installation closure.

A wheelhouse and index can be supplied together. If they offer equally preferred
wheels for the same pin, preparation refuses the ambiguity. For an unreleased
candidate sharing a version number with a published artifact, use a complete
local wheelhouse without an index.

`plugins catalog resolve` continues to verify/export an already populated local
catalog and wheelhouse. It does not acquire packages. `plugins install`, `lock`,
`sync` and `catalog resolve` retain their offline boundaries. Only an explicit
`prepare --index-url HTTPS_URL` authorizes index access in this workflow.

## Targets and integrity

The recorded target includes implementation, exact Python version, operating
system platform, machine and ABI. `resolver_platform` also records the exact
uv platform triple, including the glibc level on Linux. This implementation supports **native CPython
3.11–3.14**, macOS arm64/x86_64 and glibc Linux aarch64/x86_64 (glibc 2.17, 2.28 or 2.31–2.40, the explicit platforms supported by uv 0.12).
`--platform native`, the measured platform, or its corresponding uv platform
triple must agree with the explicit interpreter. macOS records the running OS,
not the interpreter's build deployment minimum. Other targets fail closed;
this is not cross-compilation.

Selection follows [PyPA's ordered compatibility tags](https://packaging.pypa.io/en/stable/tags.html)
for that interpreter. Exact ABI and platform preference can disambiguate native
wheels; two candidates with the same best priority are refused. A valid hash
from another platform cannot make that wheel compatible. A preferred wheel
with an unadmitted hash cannot cause fallback to a weaker candidate.

Apizr does not choose an arbitrary hash. It selects the wheel compatible with
the requested target, verifies its exact bytes against hashes admitted by the
resolver, then writes a lock bound to that artifact. Wheel metadata and embedded
plugin identity are also verified. A final **offline** resolution checks that
the retained wheels form the exact dependency closure. Hashes establish
integrity, not author trust: review the plugin code before installation.

Preparation uses compatible wheels only. If one is unavailable, Apizr stops
instead of compiling dependency source. No setup.py, source build backend or
compiler is started. The strict existing installer still accepts exactly one
SHA-256 per exact pin.

## Results, limits and refusals

The versioned [result schema](../specs/apizr-plugin-preparation-v1.schema.json)
reports `prepared`, `refused` or `interrupted`, with structured diagnostics.
Preparation output contains no absolute temporary paths or credentials. Index
URLs must use HTTPS without embedded credentials or query strings. Resolver
configuration, proxies, keyrings and user environment credentials are not inherited.

The output directory must be new, even if an existing directory is empty.
Preparation verifies everything privately, then publishes the completed export
using the existing exclusive directory publication pattern. A refusal removes
staging; cancellation terminates/reaps subprocesses and publishes no incomplete
wheelhouse. Existing output and symlink parents are refused.

Bounds include 1 MiB of resolver requirements, 512 admitted hashes per pin,
128 retained wheels, 64 MiB per wheel, 256 MiB total compressed bytes and
512 MiB total expanded bytes. Candidate enumeration is bounded at 16,384 entries;
resolver output is at most 8 MiB and stderr at most 64 KiB. Default runtime is
120 seconds; `--timeout-ms` accepts up to 600,000 ms. Wheel archive protections
also apply. Identical target, resolver version and artifact evidence produce
identical lock and manifest bytes regardless of location, input ordering or
`PYTHONHASHSEED`.

| Diagnostic reason | Action |
| --- | --- |
| `preparation_extra_required` | Install the same core build with `[preparation]`. |
| `invalid_resolver_lock` | Supply exact pins with admitted SHA-256 hashes. |
| `interpreter_unavailable`, `target_invalid` | Supply an executable absolute interpreter and matching native platform. |
| `compatible_wheel_unavailable` | Obtain a prebuilt wheel for the named distribution/target. |
| `wheel_selection_ambiguous` | Supply an unambiguous reviewed artifact source. |
| `wheel_hash_not_admitted` | Investigate the source/lock mismatch; do not add the observed hash blindly. |
| `artifact_download_failed`, `resolver_refused` | Check explicit source availability; private tool output remains redacted. |
| `preparation_timeout`, `preparation_cancelled` | Retry explicitly when ready; no partial export is retained. |
| `output_exists` | Select a new output directory. |

Passing a valid multi-hash resolver lock directly to `plugins install` still
returns `invalid_requirements_lock`, with a typed `suggested_operation: prepare`
hint identifying the affected distribution.
