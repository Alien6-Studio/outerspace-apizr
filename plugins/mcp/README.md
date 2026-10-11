# outerspace-apizr-mcp

Core and all three optional plugins are published on PyPI at **0.4.5**.
Use matching versions; see the release record for verification and directory status.

<!-- mcp-name: io.github.Alien6-Studio/outerspace-apizr -->

Analyze a local Python project from an MCP client without executing its functions.
Default mode exposes exactly three read-only tools. The published **0.4.2** version also supports opt-in
status/run/resume for an existing
delivery request selected by the operator with `--delivery-request`. Clients
cannot choose operational paths, credentials or keys. Existing per-operation
grants remain required; delivery uses the shared coordinator and may mutate
registry/proof state.

This optional Apizr plugin runs in its own Python environment. Use the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile)
to choose the matching catalog profile and verified target artifacts. The
[release record](https://apizr.outerspace.sh/releases/0.4.5/) describes the
functionality and validation for **Apizr 0.4.5**.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Development
locks, activations and permissions are not migrated automatically.

## Registry installation (0.4.5)

The `outerspace-apizr-mcp` command delegates to `apizr mcp serve`. Follow the short
[Registry installation guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/#registry-installation)
to create/select the project file, review an explicit analysis policy, and prepare
the separate managed plugin store. Supply their absolute paths through the three
required arguments `--project`, `--operator-policy` and `--plugins-dir`.
Install and activate the matching MCP plugin
in that separate store first. Installing this launcher through a registry client
does not install or activate the governed plugin, grant access to a project, or
enable delivery. Startup retains the existing admission checks and isolated
plugin interpreter. No hosted endpoint is provided.

The repository's `server.json` describes the published Official MCP Registry
0.4.5 entry. The MCPB wrapper is attached to the immutable GitHub Release and
uses the same explicit inputs and admission checks. Smithery distribution and
Glama indexing remain unverified; see #279 and the release record.
Use matching 0.4.5 core/plugin versions.

See the [plugin guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/).
Python 3.11–3.14. GPL-3.0-or-later; the full license is included.
