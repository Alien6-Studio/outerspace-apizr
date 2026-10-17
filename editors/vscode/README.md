# Apizr for VS Code — 0.4.6 development

An in-repository, GPL-3.0-or-later workspace extension. It calls your explicitly
selected installed engine over `apizr.editor/v1`; it contains no Python engine,
scientific libraries, runtime npm dependency or automatic installer. VS Code
1.140 or newer is required so 64-bit integers and original float tokens survive
JSON rendering exactly; scientific comparison still runs only in Python.

Open a trusted native project folder, select **Apizr: Select engine**, and set
`apizr.operatorPolicy` to the absolute operator policy file. `apizr.project`
defaults to `apizr.toml`. If its declared root differs from its directory, set
`apizr.projectRoot` to that exact root (absolute or workspace-relative). `apizr.store` defaults to `.apizr/experiments/v1` and must
match an exact `history.read` grant in that policy. The engine enforces all source
scope, evidence validation and authorization. **Apizr: Check engine** discovers
the actual protocol; it does not infer compatibility from a package version.

Use a Python interpreter/venv containing the engine, or select the absolute
`apizr` executable of an existing `uv tool` installation. The extension never runs
`uvx`, downloads an engine or installs a dependency. Paths refer to the workspace
extension host, including in an SSH/Dev Container window, not to the UI computer.
Native Linux/macOS hosts and Remote SSH to Linux are qualified. The retained
SSH case uses a macOS UI, Linux ARM64, Python 3.14 and the installed candidate
wheel in the real workspace extension host. Dev Containers and other remote
transports are unqualified. Windows-native engines, browser/virtual
workspaces and ambiguous multi-root commands are refused with an actionable
message; select a source in the intended native workspace folder.

**Apizr: Inspect with Apizr** inspects the saved `.py` or `.ipynb` file. Unsaved
changes are explicitly excluded; subsequent changes mark the view outdated. The
Inspection tree exposes canonical sections and source/cell navigation. A bounded
read-only JSON document retains the complete engine result, including unknowns
and diagnostics. No model is executed, and no analysis runs on typing. Optional
`apizr.inspectOnSave` is false by default. Use the progress cancellation button
or **Apizr: Cancel current operation**; each engine process also has a deadline
and byte/chunk limits.

**Apizr: Refresh runs** reads validated history through the engine. Select a Run
for its complete intended Plan and observed Run; select two for an engine-produced
comparison, including canonical finite deltas and unknowns. No validation or diff
is reimplemented here. After the first explicit refresh, VS Code's file-create
events for published Run JSON trigger a coalesced engine refresh. The extension
never polls, reads or indexes the store itself. **Apizr: Open recorded source**
opens the current file at the recorded reference when available; a missing source
or notebook cell index is not guessed. Inspection locations carry exact cell
indexes; Run evidence may identify a cell without retaining its notebook index.

Telemetry is **off by default**. The status, enable, disable and preview commands
control bounded local counters only. `apizr.telemetry.enabled` is a global user
setting. VS Code's `isTelemetryEnabled` signal and global `telemetryLevel` must both
allow usage telemetry (`all`); the stricter decision wins. Every child inherits
that decision through `APIZR_TELEMETRY_ALLOWED` and `APIZR_TELEMETRY`. CI, served
processes and explicit core opt-outs still win. Disabling clears the last in-memory
usage preview. There is no sender, production DNS/socket attempt or event spool.
The preview displays the engine's exact local payload for the last operation.

Build with `npm ci --ignore-scripts` then `npm run compile`. The pinned development
tools are TypeScript and Node/VS Code type declarations only. Source ships with
the VSIX alongside compiled JavaScript and the repository licence. This development
package is not published automatically to Marketplace or Open VSX.
