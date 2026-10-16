# Python 3.15 qualification — 0.4.6 development

This implements the development and qualification work in #330 on `0.4.6`.
The exact four-package candidate was built from
`2fa3eb161a9f8437256ba13096bbe6cda78206fd`. Candidate package metadata remains
0.4.5 until the coordinated version promotion in #326. Nothing here publishes a
package, image, tap, version tag or stable-site update.

## Compatibility and dependency choices

The core, three plugins, MCP launcher and generated targets admit Python
3.11–3.15. Existing 3.11–3.14 qualification jobs remain. Linux and macOS 3.15
jobs extend full compatibility, installed distributions, containers, MCP and
plugin preparation. New candidate inventories declare all eight installation
targets; export preparation refuses incomplete or mislabeled target sets.
Historical candidates retain their six-target requirement. The Action admits
3.15 explicitly while its default stays at 3.14 for its published core default.

HTTP/MCP extras retain Uvicorn, uvloop, httptools and websockets explicitly;
they no longer pull the unused Rust reload watcher. `lock-extension.json`
records added 3.15 wheels. All retained dependency versions, source archives and
pre-existing wheel identities are unchanged. Watchfiles and python-dotenv are
removed. The license inventory covers the resulting 146 registry entries.

Only PyYAML uses a source exception during explicit dependency preparation:
its exact locked source is hash-verified, native compilation is disabled, and
a universal pure-Python wheel is retained. `pyyaml-build.json` binds both
artifacts. Offline clients installations consume this wheel; every other
runtime dependency still requires an upstream binary. Production plugin
preparation retains binary-only admission. The plugin checker admits the
regular stable-ABI member of compressed `abi3.abi3t` wheels, with conservative
version/build/CPU/platform checks retained. See [PEP 803](https://peps.python.org/pep-0803/).

The scientific example keeps NumPy 2.4.6 and SciPy 1.17.1 on 3.11–3.14.
Markers select their binary-compatible 2.5.4 and 1.18.1 versions on 3.15.
`science-requirements.json` retains the exact workload input. These libraries
are workload dependencies, not additions to the Apizr core.

## Installed proofs

`candidate.json` retains eight exact archive identities. The core wheel contains
only the same canonical package layout. Archive contents and metadata are checked
against the final production tree. Qualification-only probe wording, workload
markers and this evidence are recorded after the candidate code commit.

`dependency-target.json` retains the 3.15/macOS-arm64 dependency export.
`installations.json` covers pip, uv, pipx, minimal core, all extras, HTTPS/SSH,
catalog/profile synchronization, experiment contracts and unchanged-core checks.
`mcp-outcome.json` covers real analysis, views, schemas, delivery, lifecycle and
registry sessions with the same retained wheels and unchanged activations.

`science-journey.json` and `science-reproduction.json` cover two notebook runs,
comparison, actual REST/MCP prediction parity, stale-model and invalid-payload
refusal, offline Python guards, retained-wheel replay and byte-identical replayed
bundles. The first journey takes 34.51 seconds; environment acquisition is
recorded separately. `science-wheels.json` records exact scientific distributions
and their license declarations; `science-audit.json` has no vulnerability finding.

`worker-image.json` identifies the disposable Linux/arm64 Python 3.15 worker,
never a published image. Installed-wheel smoke exercises direct/local/OCI and
strict repository interfaces. Kernel checks and cleanup results are recorded in
`qualification.json`. The final ten kernel/transport/cleanup checks pass.
An earlier broader attempt was stopped at an observer-timing failure (12 passed);
the detached-child case passes alone. Its observer now reads the heartbeat with
`cat`, accepts only numeric samples and reports probe/response diagnostics. The
policy bounds, deadlines and safety assertions are unchanged.

`homebrew-offline-build.json` proves isolated PEP 517 construction with the six
unchanged build wheels, denied networking, empty cache, no runtime build tools,
and a separate official Pydantic provider. The runtime excludes global
site-packages and uses the declared provider through `homebrew_deps.pth`.
`homebrew-formula.json` proves real installation, audit/test, doctor/completions,
plugin lifecycle and unchanged Cellar contents on this physical Apple Silicon
Mac with Python 3.15. The temporary keg-only probe is uninstalled and its tap
removed; the existing Apizr installation is preserved. Historical physical
qualification records are not rewritten.

## Tests and limits

One common Python 3.15 suite passed 7,598 tests with 75 skips in 303.84 seconds.
Two qualification-test failures collected before their fixes passed subsequent
focused qualification. The final focused run passed 1,139 tests; 123 relevant
tests also passed on Python 3.11. All 39 documentation publication tests passed
with their dedicated dependencies, including the optional test skipped without
`ghp-import` in the common environment. Coverage after focused qualification is
97.44%, with the existing global and selected-evidence gates retained.

The previous CI's only underlying failure was its historical 0.4.4 example
using imports introduced after that version. A compatible frozen authorization
example now qualifies 0.4.4; the current guide is exercised with the candidate.
Historical 0.3 installation examples use Python 3.14 when the candidate host is
3.15, preserving the published distributions' original interpreter bounds.
Actual current/historical README and REST/MCP examples pass outside the checkout.

Digest-only maps are exported as explicit name/SHA-256 records; raw local
proofs remain in the qualification directories.

Ruff, Pyright, both architecture gates, pre-commit and the ten locked dependency
audits pass. CI verifies the expanded Linux/macOS matrices separately; local
macOS/Docker evidence is not evidence of every hosted target. Publication and
public verification of the coordinated 3.15 assets remain under #326 and the
publication acceptance item in #330.
