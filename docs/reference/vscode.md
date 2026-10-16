# Inspect and compare in VS Code

The **0.4.6 development extension** lives in `editors/vscode/` under the repository's
GPL-3.0-or-later licence. VS Code 1.140 or newer is required for lossless
numeric-token rendering; 64-bit integers and original float tokens are preserved. It uses an installed development engine supporting
`apizr.editor/v1`; the published 0.4.5 engine does not provide this editor contract.
The extension is not automatically published to Marketplace or Open VSX.

Install the qualified VSIX using **Extensions → Install from VSIX**, open your
trusted native project folder, then run **Apizr: Select engine**. Select either
the Python interpreter of a venv containing the candidate engine and its notebook
extra, or an existing `apizr` executable installed through `uv tool`. Nothing is
downloaded or installed when a window opens.

Set these values in Settings:

| Setting | Meaning |
| --- | --- |
| `apizr.engine.mode` | `python` interpreter/venv or installed `executable`. |
| `apizr.engine.python` / `apizr.engine.executable` | Absolute engine path in the workspace extension host. |
| `apizr.project` | Project file; default `apizr.toml` in the selected folder. |
| `apizr.projectRoot` | Exact declared project root, absolute or workspace-relative; empty uses the project file directory. |
| `apizr.operatorPolicy` | Absolute operator policy file. |
| `apizr.store` | Project-relative history store; default `.apizr/experiments/v1`. |
| `apizr.timeoutMs` | Engine deadline from 500 to 120,000 ms; default 30,000. |
| `apizr.inspectOnSave` | Explicit opt-in; default false. |

**Apizr: Check engine** discovers the protocol and supported operations before
project evidence is requested. An incompatible engine is refused with a clear
message. The [operator policy](operator-policy.md) must grant `source.analyze` for
the exact project and, for Runs, `history.read` for the exact store. The extension
cannot enlarge those permissions. Restricted Mode launches no engine and disables
project operations; only local telemetry settings remain accessible.

## Inspect the saved file

Run **Apizr: Inspect with Apizr** on a saved Python script or notebook, using the
command palette or file context menu. The Inspection tree presents the engine's
canonical sections and locations; a read-only JSON document retains the complete
result and diagnostics. Select a located tree item to open its source line or
notebook cell. Unsaved changes are explicitly excluded. Editing or saving the
source marks the result outdated until a fresh inspection completes.

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
The separate global Apizr opt-in and VS Code's global usage-telemetry permission
must both allow collection. Every child receives the stricter decision. The
preview shows the engine's exact bounded payload; there is no production sender.
No source, path, metric or Run identity is included in a usage report.

Native macOS qualification runs the real installed extension in clean trusted
and untrusted profiles; the CI job qualifies native Linux with the same candidate
wheel. An interpreter/venv and an installed `uv tool` executable are explicit
engine modes. The extension declares `extensionKind: workspace`, so remote paths
refer to the remote extension host. **A real SSH/Dev Container session remains
to be qualified in #312**; declaration alone is not remote qualification.
Windows-native engines, virtual/browser workspaces and multi-root commands with
no selected project are currently unsupported and refused explicitly.

The [distribution procedure](../contributing/vscode-distribution.md) describes the
reproducible build, dependency/notice gates and separate publication decision.
