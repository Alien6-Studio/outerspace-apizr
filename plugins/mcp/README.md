# outerspace-apizr-mcp

Apizr **0.4.6**: use the matching core and plugin versions together.

<!-- mcp-name: io.github.Alien6-Studio/outerspace-apizr -->

Analyze a local Python project from an MCP client without executing its functions.
Apizr 0.4.6 adds read-only experiment list/show/diff to the three
analysis tools. History requires a separate `history.read` grant for the configured
project's store; installation and `source.analyze` grant no history permission.
Use matching core/plugin versions for these tools. The existing delivery path supports opt-in
status/run/resume for an existing
delivery request selected by the operator with `--delivery-request`. Clients
cannot choose operational paths, credentials or keys. Existing per-operation
grants remain required; delivery uses the shared coordinator and may mutate
registry/proof state.

This optional Apizr plugin runs in its own Python environment. Use the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile)
to choose the matching catalog profile and verified target artifacts. The
[release record](https://github.com/Alien6-Studio/outerspace-apizr/blob/v0.4.6/docs/releases/0.4.6.md) describes the
functionality and validation for **Apizr 0.4.6**.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Existing
locks, activations and permissions are not migrated automatically.

## Registry installation

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

The repository's `server.json` identifies the matching Apizr 0.4.6 package.
Registry publication is separate from package publication. The prepared MCPB wrapper uses the same explicit inputs and admission
checks for later Smithery submission; no hosted endpoint or implicit delivery is
introduced. Use matching Apizr 0.4.6 core/plugin versions together.

See the [plugin guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/).
Python 3.11–3.15. GPL-3.0-or-later; the full license is included.
