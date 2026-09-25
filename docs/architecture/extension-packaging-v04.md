# V04-01 — Separate extension packaging

!!! note "Prototype architecture record"

    This page preserves the original separation experiment. For the current,
    unreleased installation/runtime commands use the [0.4 development guide](../development/0.4.md).

Implementation updates: [controlled invocation](../reference/extension-invocation.md)
and [local installation/inventory](../reference/local-extensions.md) now provide
reusable operations. The record below describes the original packaging experiment.

Status: proposed 0.4 architecture, demonstrated by a private experiment; **not a
production plugin runtime**. See the [roadmap and qualification record](../contributing/0.4-roadmap.md).
The package version remains 0.3.0. No public CLI command is added.

## Decision and boundaries

Keep Python analysis, canonical contracts, selection, exposure planning and
extension-result validation in the core. Lightweight included adapters load only
when used; the planned official Git adapter requires an explicitly installed Git.
Optional OCI, MCP, Postman and Continuum Attest integrations belong in separately
installed extensions. One OCI integration serves compatible destinations, including
Docker Hub, GHCR and Trunx. These integrations are roadmap items, not delivered here.

CLI, CI and a future Apizr MCP server call the same typed core operations. The path
is **MCP transport → core operation and local authorization → approved extension**;
no interface scrapes human CLI output or duplicates compilation. Apizr's own MCP
server differs from the business MCP servers it generates. The extension protocol
is local IPC, not MCP, and has no dependency on the MCP SDK.

Use an already installed **uv** executable as the installation backend: `uv venv`
with an explicit interpreter, then `uv pip install --python <plugin interpreter>`.
No backend/bootstrap download, interpreter download or pip fallback is implicit.
If uv is absent, diagnose the prerequisite before changing anything. Downloads of
approved plugin packages are a separate, explicit installation operation. This
experiment installs a locally built wheel offline with `--no-index --no-deps`.
It adds no dependency to Apizr's runtime or universal lock.

Installing into the core with pip, `uv tool --with`, or `pipx inject` would couple
resolution and mutate the core, so is rejected for the new protocol. In-process
entry points remain only for the historical API. A new package resolver is
unnecessary; uv already provides the environment and installation primitives.
Using pip inside each venv would also work, but would require bootstrapping pip and
a second installer workflow. uv is an explicit external prerequisite, not a
transitive core dependency.

## Minimal versioned contract

The experimental module `apizr._prototypes.extension` is installed in the wheel,
but is absent from production dispatch and entry points. It creates a canonical
Capability IR through the installed core, hashes it and invokes a reviewed absolute
plugin interpreter using `-I -B -m apizr_extension_probe`. The demo package imports
only the standard library. One JSON request is sent on stdin; one JSON response is
returned on stdout; stderr is diagnostic only. Exit failure or a ten-second timeout
fails the operation, without fallback or retry.

| Field | Request | Response |
| --- | --- | --- |
| `protocol` | `apizr.extension-probe/v1` | Same exact version |
| `request_id` | `packaging-proof` (one-shot experiment) | Same value |
| `operation` | `describe` | Same operation |
| `source_digest` | Core canonical artifact digest | Nested under `result` |
| `result.message` | — | `demo extension reached` |

The core strictly validates types, required fields, extra fields, exact protocol,
operation, request identity and source digest correspondence. Non-JSON, incompatible
versions and unexpected results fail. This is a prototype contract, not a promise
that `describe` will become a production operation. A breaking wire change uses a
new protocol version; there is no permissive downgrade or version coercion.
Future operations must specify their own typed payloads, canonical artifacts and
explicit permissions. An extension cannot change the meaning of existing contracts.

## Environments and lifecycle

The proposed user-owned data root is `$XDG_DATA_HOME/apizr/plugins` (default
`~/.local/share/apizr/plugins`) on Linux and
`~/Library/Application Support/apizr/plugins` on macOS. A future explicit local
override may support CI. Each approved distribution/version/interpreter combination
gets its own environment; updates create a new environment before switching an
explicit activation record. Failed staging can be removed; uninstall removes only
the selected plugin environment after deactivation. Never write into the core's
`sys.prefix`, uv tool environment, pipx environment or Homebrew Cellar.

The experiment implements **none** of the registry, activation persistence,
upgrade or garbage collection machinery. Its caller supplies a fresh external
work directory, retained with evidence for review, and removes it explicitly later.
Core and extension installations are separate from activation (selecting the
operation's extension) and authorization (operator approval of code and effects).
Installed does not imply active or authorized.

uv tool and pipx installations can launch an external interpreter without changing
their environments. Homebrew owns the core formula's `libexec`; extensions stay
outside the formula prefix and survive independently of a formula replacement.
Interpreter removal/upgrades can break a plugin venv: report it and require an
explicit rebuild, never repair or download during invocation. The current
experiment is POSIX-only; Windows paths and process behavior remain unqualified.

`apizr.pipeline.v1` keeps its existing trusted, explicitly selected, in-process
contract and same-environment installation. Existing `notebook`, `http`, `mcp` and
`legacy` extras and public commands remain unchanged. Moving optional functionality
in future tickets requires compatibility decisions; this ADR does not remove extras.
Dependencies of generated applications remain distinct from compiler/extension
dependencies. Static analysis never installs application dependencies.

## Trust and limits

A venv and child process are **not a sandbox**. Plugins are explicitly approved
code with the user's filesystem/network privileges. The experiment demonstrates
that a benign plugin needs no core mutation; it does not prevent malicious mutation.
The immutable before/after evidence hashes bytes, modes, symlink targets and the
file set, plus installed distributions. It does not establish provenance or code
innocuity, and does not hash shared interpreter files outside the core prefix.

A remote repository must never authorize plugin installation, execution of its
code, credentials, or artifact publication. No remote configuration is consumed
by the experiment. Publication is not service deployment. Attestation verifies
specific provenance claims, not safety. Production output bounds, process-tree
cleanup, cancellation, structured failures, concurrent requests, authorization
storage and crash recovery remain future work. `capture_output` here assumes the
reviewed tiny demonstration, not an untrusted or unbounded extension.

## Qualification and reproduction

Run from the checkout with an already installed uv and Python 3.11–3.14:

```sh
uv run --locked pytest tests/test_extension_probe.py tests/test_pipeline_plugins.py tests/test_optional.py
uv run --locked python scripts/smoke_extension_packaging.py --work-dir /tmp/apizr-v04-uv
```

Use a fresh directory each time. The driver builds the wheel, uses real
`uv tool install`, builds and installs the demo separately, launches the installed
core with isolated imports from an external cwd, rejects incompatible protocol in
both directions and writes complete `evidence.json`. No import from `src/` can
satisfy the proof. Unit tests additionally verify missing uv causes no process or
filesystem operation and that the integrity inventory detects changes.

For **real Homebrew**, prepare a local-only fixture using Python 3.14 (wheel tags
must match Homebrew's Python and host architecture):

```sh
uv run --locked --python 3.14 python scripts/prepare_extension_homebrew.py /tmp/apizr-v04-brew
HOMEBREW_NO_AUTO_UPDATE=1 brew tap apizr-v04/prototype file:///tmp/apizr-v04-brew/tap
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 brew install --ignore-dependencies --build-from-source apizr-v04/prototype/apizr-v04-probe
HOMEBREW_DEVELOPER=1 brew test apizr-v04/prototype/apizr-v04-probe
uv run --locked python scripts/smoke_extension_packaging.py \
  --work-dir /tmp/apizr-v04-brew-proof \
  --core-python "$(brew --prefix apizr-v04-probe)/libexec/bin/python" \
  --core-root "$(brew --prefix apizr-v04-probe)"
brew info --json=v2 apizr-v04/prototype/apizr-v04-probe > /tmp/apizr-v04-brew-proof/homebrew-receipt.json
```

On an existing workstation, first verify `brew list --versions python@3.14 uv`
and their dependencies are installed. `--ignore-dependencies` is a Homebrew
development-only option for this test fixture: it avoids upgrading workstation
dependencies. Omit it only on a disposable runner where dependency installation
and upgrades are intended. `HOMEBREW_NO_AUTO_UPDATE` alone does not prevent them.

Preparation downloads only five base wheels referenced in the existing lock and
verifies their SHA-256 hashes. Homebrew installs the core and those wheels offline
into a real formula `libexec`. The fixture is local, never published; it is not a
release formula or evidence of admission to Homebrew. The source archive contains
reviewed third-party wheels only for local testing, not for redistribution. The
local tap commit uses the configured identity and DCO sign-off. Retain evidence,
then clean up with `brew uninstall apizr-v04-probe` and
`brew untap apizr-v04/prototype`; remove only the selected temporary directories.

| Configuration | Testable scope |
| --- | --- |
| Linux / Python 3.11–3.14 / uv tool | Dedicated CI matrix, real wheel and plugin installs |
| macOS / Python 3.11 and 3.14 / uv tool | Dedicated CI matrix |
| macOS / Homebrew Python 3.14 | Real local formula installation and full prefix inventory |
| Linux Homebrew, pipx, Windows | Compatible design where applicable, not yet qualified |

The [qualification record](../contributing/0.4-roadmap.md) distinguishes actual
results from prepared CI. A simulated Cellar directory is never Homebrew evidence.

References: [uv tool environment ownership](https://docs.astral.sh/uv/concepts/tools/),
[Homebrew Python guidance](https://docs.brew.sh/Python-for-Formula-Authors).
