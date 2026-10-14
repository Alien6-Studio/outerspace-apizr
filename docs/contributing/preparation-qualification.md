---
title: Native preparation qualification
description: Resolver series, measured native platforms and evidence required to extend plugin preparation.
---

# Native preparation qualification

The 0.4.6 development line qualifies uv **0.12.x and 0.13.x** explicitly.
Its CI and Glama hosting recipe pin **0.13.1**. Acceptance is per stable series;
patch releases remain accepted and their exact version appears in
`preparation.json`. A new series or prerelease returns
`resolver_version_unsupported` before resolution. The CLI names the accepted
series and explains `--uv`. Publication workflows and published 0.4.5 are kept
separate until the final release qualification and approval.

## Why the previous bounds existed

The 0.12-only check bound the measured resolver implementation used by the
original installed proofs. It was not a claim that every newer uv was broken.
Preparation depends on these behaviors:

- `pip compile` emits exact requirements with admitted SHA-256 hash sets.
- Binary-only resolution never builds dependency source or downloads Python.
- Universal, dependency-free `pylock.toml` enumeration retains wheel URLs,
  names and hashes within the existing bounds.
- A second offline resolution of retained wheels reproduces the exact closure.
- Incompatible wheels produce a redacted `compatible_wheel_unavailable`
  diagnostic; private resolver output never becomes public evidence.
- No configuration, credentials, proxy or keyring authority is inherited.

[uv 0.13's release notes](https://github.com/astral-sh/uv/releases/tag/0.13.0)
change the default Python, constraints handling, virtualenv startup patches and
archive handling. Apizr supplies an installed interpreter explicitly, disables
Python downloads, parses bounded exact hash locks and prepares wheels only.
The proofs still exercise actual installation and secure refusal behavior;
compatibility is not inferred solely from the release notes.

glibc 2.40 was the last explicit triple listed by uv 0.12. uv 0.13 retains that
limit. A `manylinux_2_41` CLI argument is rejected by both series. For a measured
glibc 2.41 Linux host, Apizr therefore uses uv's **native resolution**, verifies
that the interpreter's architecture matches the current Linux host, and records
`native-x86_64-glibc-2.41` or `native-aarch64-glibc-2.41`. PyPA's native wheel tags
remain authoritative for artifact selection. Older accepted glibc versions keep
their explicit triples. musl, foreign hosts and unqualified glibc 2.42 remain
`target_invalid`; there is no automatic forward libc allowance.

## Repeatable evidence

`scripts/plugin_preparation_matrix_proof.py` builds the four coordinated wheels
once for its host, downloads native dependencies against the unchanged hash lock,
and installs the candidate preparer outside the checkout. It proves core
resolution and separate MCP, OCI and Attest preparation. Every retained artifact
hash must be admitted and equal the strict installer lock. Preparation leaves
the profile empty and the preparer and global plugin state unchanged.

The reusable `Plugin preparation qualification` workflow is called by
`MCP server plugin`, preserving that workflow's existing qualification jobs:

| Target | uv versions | Evidence |
| --- | --- | --- |
| macOS ARM, CPython 3.14 | 0.13.0, 0.13.1 | Core and all three prepared plugin closures |
| macOS Intel, CPython 3.14 | 0.13.0, 0.13.1 | Core, OCI, Attest; secure locked MCP refusal |
| Linux x86_64, CPython 3.11 | 0.13.1 | Core and all three prepared plugin closures |
| Debian 12, glibc 2.36, CPython 3.14 | 0.12.0, 0.13.0, 0.13.1 | Explicit platform resolution and all closures |
| Debian 13, glibc 2.41, CPython 3.14 | 0.12.0, 0.13.0, 0.13.1 | Native resolution and all closures |

Local qualification additionally runs Debian 13 on aarch64. The container proof
asserts the actual libc version; it does not mock Linux target facts. CI retains
the image identity, candidate wheel hashes, measured target/resolver, preparation
manifests and exact locks. macOS Intel cannot prepare the secure locked MCP
closure because its locked cryptography version has no compatible wheels. The
existing `plugin_preparation_intel_proof.py` verifies that refusal without a
source build, dependency downgrade, installation or activation.

For a local host with uv on PATH:

```sh
uv run --no-project --python 3.14 python scripts/plugin_preparation_matrix_proof.py \
  --output /absolute/new/workspace
```

The existing MCP smoke proof also calls `plugin_preparation_proof.py` to install
the prepared profile, leave activation explicit and exercise the real MCP client.
Preparation compatibility does not replace serving, OCI isolation, security or
release qualification.

## Adding a series or libc

Review resolver release notes and repeat the matrix with the candidate series.
Keep the existing format, hash, binary-only, bounds, offline closure and refusal
checks. For a new libc, verify both native tags and the resolver's actual accepted
mode on a real host, alongside an older baseline. Change the explicit allowance
only with that evidence, then update documentation and development pins together.

`scripts/check_uv_policy.py` reads the production allowance and qualification
pin, checks development workflow pins and queries Astral's latest stable release.
The weekly workflow runs this guard without rerunning the full preparation
matrix. A newly published unqualified series fails early with a request to run
the proofs. It never updates dependencies or publishes a package automatically.

The root `Dockerfile` builds Glama's analysis server from the official `0.4.6`
development ref on Debian 13 with uv 0.13.1 and explicit CPython 3.14.
`SOURCE_COMMIT` optionally requires an exact source SHA during qualification.
Its build context includes only the recipe; it clones the public source explicitly
and runs as an unprivileged user. This recipe
is separate from OCI service images generated by the OCI plugin.
