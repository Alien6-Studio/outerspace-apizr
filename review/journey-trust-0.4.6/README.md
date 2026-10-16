# Executable documentation and trust boundaries (#323, #324)

This batch qualifies the installed core candidate from `1b9f6d5f` and the existing
VSIX. `qualification.json` records their exact hashes. Packaged engine Python,
TypeScript and README inputs are unchanged; qualification scripts, tests and
documentation are updated. The parent CI completed successfully with 80 successful
jobs and 17 intentional skips. No publication or complete milestone qualification
is claimed.

| Evidence | Observed result |
| --- | --- |
| `executable-docs.json` | Existing inspection/run/comparison/exposure examples plus all five marked SDK quickstart blocks run verbatim with the installed candidate outside the checkout. One session, two decorated variants, shared history, v2 comparison, provider disablement and disabled telemetry preview pass. |
| `jupyter.json` | The exact documented notebook executes in real isolated ipykernels; three successful captures retain expected modes and unknown memory-source evidence. Separate cases prove repeated/unsaved cells, display preservation, decorator rebinding, interrupt/cancel and recovery. |
| `cli-sdk-security.json` | Thirteen real Python processes, including the trusted CLI workload worker, make zero DNS/INET attempts. Valid unauthorized project inspection refuses before its Python source can be opened. Corruption returns `store_corrupt`; provider disablement does not prevent historical reads. |
| `sensitive-preview.json` | Explicit opt-in captures only the two coarse success/failure counters. Private parameter/metric names and values, local artifact path, remote input URI and exception text are absent; scientific records have no telemetry fields. Transmission remains unavailable. |
| `vscode-trusted.json` | Actual installed VSIX in VS Code 1.140.0/macOS, installed candidate interpreter: canonical inspection, saved/stale buffer handling, CLI/SDK/Jupyter history, show/diff, publication refresh, global opt-out and incompatible-engine refusal pass. Twenty-four Apizr processes (25 guarded Python processes overall) make zero DNS/INET attempts. |
| `vscode-restricted.json` | Actual Restricted Mode: zero Apizr starts, including the telemetry control; no connection attempts. Both cumulative spawn instrumentation and Python admission signals verify the result. |
| `security-mutations.json` | All 172 mutants killed. New mutations cover malformed SDK metrics, aggregate payload bound, concurrent task authority, finalization context cleanup, corrupted record digest and failed-provider unknown state. |

The guard is temporary qualification instrumentation in an explicitly selected
disposable virtualenv. It is installed after UI fixture preparation and removed
in `finally`, including when the measured phase fails. Each guarded environment
is reserved to one phase. Real DNS and direct socket connection attempts are
denied as positive controls before the measured log is reset. Logs retain only
PIDs and fixed event names. The native tests verify detection and cleanup.
This covers Python DNS/INET events; it is not a native-code sandbox and does not
govern VS Code's own Electron services or the SSH transport. Remote qualification
retains its existing separate scope.

Compatibility references in
`tests/fixtures/experiments/compatibility-0.4.5` were generated independently by the
exact `v0.4.5` source (`da74e6de`) over the existing real frozen 0.4.5 captured
store. That source was exported to a separate directory and its import origin
asserted. Its `history_bytes(show_run(...))`, `diff_bytes(compare_runs(...))` and
`diff_text(...)` outputs are frozen with hashes and the input-store provenance.
The installed candidate reproduces Plan/Run admission, CLI canonical show/export
and JSON/text diff byte-for-byte. New mixed-history list views and new v2 records
have their documented independent contracts.

Validation: 371 focused Python tests, then 57 final qualification/structure tests,
14 Node tests, all 172 security mutants, package/script architecture, Ruff,
Pyright, strict MkDocs and 127-page HTML validation pass. Tests are grouped around
the changed qualification surfaces; the unchanged engine's full suite is not
repeated locally. CI runs the new offline proof against each installed candidate
target through `qualify_distributions`; the existing VSIX jobs run the guarded
native proof and retain its JSON/log files. Jupyter and executable-doc checks
remain in their existing blocking jobs.

The complete integrated journey remains #325. Python 3.15, legacy removals and
release packaging/publication retain their separate milestone gates. Private
telemetry collector work and Academy recordings remain deferred to #335/#334.
