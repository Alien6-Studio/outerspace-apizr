# Inspect and compare in VS Code

For a complete example with real data and measured Runs, follow the
[illustrated Academy lesson](../academy/vscode.md).

The **Apizr 0.4.6 extension** is developed in
[`outerspace-apizr-vscode`](https://github.com/Alien6-Studio/outerspace-apizr-vscode)
under GPL-3.0-or-later. VS Code 1.140 or newer is required for lossless
numeric-token rendering; 64-bit integers and original float tokens are preserved. It uses an installed Apizr 0.4.6 engine supporting
`apizr.editor/v1`.
The extension is not automatically published to Marketplace or Open VSX.

Install the qualified VSIX using **Extensions → Install from VSIX**, open your
trusted native project folder and accept **Install CLI**. This first-use setup
installs the matching CLI with notebook support into extension-owned storage,
then selects it automatically. Python 3.11–3.15 must be available in this extension
host. No download starts until you accept the setup action; Restricted Mode
cannot install or start the engine. **Apizr: Open CLI terminal** opens a terminal
with that CLI on its path. Project environments and notebook kernels are separate.

The current development descriptor pins an exact official Git commit, so this
setup also requires Git. It does not attempt to download an unpublished 0.4.6
package from PyPI. Switching the descriptor to a published version remains a
separate release decision. **Apizr: Select engine** can instead select your own
Python environment or an existing `apizr` executable, including a `uv tool` install.

Set these values in Settings:

| Setting | Meaning |
| --- | --- |
| `apizr.engine.mode` | `managed` CLI by default, or existing `python`/`executable`. |
| `apizr.engine.python` / `apizr.engine.executable` | Absolute engine path in the workspace extension host. |
| `apizr.project` | Project file; default `apizr.toml` in the selected folder. |
| `apizr.projectRoot` | Exact declared project root, absolute or workspace-relative; empty uses the project file directory. |
| `apizr.operatorPolicy` | Absolute operator policy file. |
| `apizr.store` | Project-relative history store; default `.apizr/experiments/v1`. |
| `apizr.timeoutMs` | Engine deadline from 500 to 120,000 ms; default 30,000. |
| `apizr.inspectOnSave` | Explicit opt-in; default false. |
| `apizr.codeLens` | Show inspection/dashboard shortcuts above saved Python files; default true. |

**Apizr: Check engine** discovers the protocol and supported operations before
project evidence is requested. An incompatible engine is refused with a clear
message. The [operator policy](operator-policy.md) must grant `source.analyze` for
the exact project and, for Runs, `history.read` for the exact store. The extension
cannot enlarge those permissions. Restricted Mode launches no engine and disables
project operations; the dashboard and local settings remain accessible.

## The Apizr workspace

Click the **Apizr bee** in the Activity Bar to open **Runs** and **Inspection**.
**Apizr: Open experiment dashboard** opens a dedicated page with validated history,
capture modes (CLI, SDK or Jupyter), recorded parameters and metrics. Select a Run
for its details; **Open complete JSON** retains the complete canonical evidence.
Opening the sidebar or dashboard starts no engine. Use **Refresh history** to load
the configured project explicitly.

## Inspect the saved file

Run **Apizr: Inspect with Apizr** on a saved Python script or notebook, using the
command palette or file context menu. The Inspection tree presents the engine's
canonical sections and locations; a read-only JSON document retains the complete
result and diagnostics. Select a located tree item to open its source line or
notebook cell. Unsaved changes are explicitly excluded. Editing or saving the
source marks the result outdated until a fresh inspection completes.

Python files also offer inspection in the editor title and CodeLens shortcuts.
Jupyter notebooks have **Inspect with Apizr** and **Open experiment dashboard**
in their notebook toolbar. A Python cell's editor context resolves to its owning
saved notebook; inspection covers the saved notebook, including when a different
Python file is open alongside it. Unsaved notebooks must be saved first.
These actions use the existing notebook editor and kernel; they do not install
or replace Jupyter or execute a cell. Experiment tracking remains explicit in
your Python/SDK or notebook code, as described in the [tracking guide](tracking-sdk.md).

No inspection runs on typing. Optional inspection on save is disabled by default.
The progress notification and **Apizr: Cancel current operation** terminate the
owned engine process. Byte/chunk limits and deadlines bound requests and responses.
Inspection never executes the inspected script or notebook.

## Browse and compare Runs

Run **Apizr: Refresh runs** to populate the Runs view. It shows up to 20 Runs from
the engine's complete validated bounded history. Expand a Run for recorded
parameters and metrics, select it for the full intended Plan and observed Run,
or select two and choose **Apizr: Compare two Runs**. Finite deltas and unknowns
come directly from the canonical Python comparison; TypeScript performs no diff
or store validation. CLI, SDK and Jupyter records share this view.

After the first explicit refresh, file-create notifications for published Run JSON
trigger a coalesced engine refresh. The extension never reads, indexes or polls the
store itself. **Apizr: Open recorded source** opens the current file when a
reference is retained. An unknown source or absent notebook cell index is never
invented; a Run's kernel cell identity does not necessarily contain an index.

## Usage controls and supported environments

**Apizr: Telemetry status / Enable local usage counters / Disable usage counters /
Preview usage report** implement the [approved policy](../about/telemetry.md).
Local counters are enabled by default when VS Code permits usage telemetry.
Set `apizr.telemetry.enabled` to `false` to opt out. Every child receives the
stricter decision, including an existing CLI opt-out. The
preview shows the engine's exact bounded payload; there is no production sender.
No source, path, metric or Run identity is included in a usage report.

Native macOS qualification runs the real installed extension in clean trusted
and untrusted profiles; the CI job qualifies native Linux with the same candidate
wheel. An interpreter/venv and an installed `uv tool` executable are explicit
engine modes. A real Remote SSH session from macOS to a temporary Linux ARM64
host also passes the same journeys with Python 3.14 and the candidate wheel;
the proof requires `remoteName: ssh-remote`. The extension declares
`extensionKind: workspace`, so engine, project and policy paths refer to that
remote host. Dev Containers and other remote transports have not been qualified.
Windows-native engines, virtual/browser workspaces and multi-root commands with
no selected project are currently unsupported and refused explicitly.

The [distribution procedure](../contributing/vscode-distribution.md) describes the
reproducible build, dependency/notice gates and separate publication decision.
