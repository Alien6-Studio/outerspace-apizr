# outerspace-apizr-mcp

This checkout prepares the coordinated **0.4.5 candidate**, not a published release.
The current public stable baseline remains 0.4.4.

<!-- mcp-name: io.github.Alien6-Studio/outerspace-apizr -->

Analyze a local Python project from an MCP client without executing its functions.
The 0.4.6 development engine adds read-only experiment list/show/diff to the three
analysis tools. History requires a separate `history.read` grant for the configured
project's store; installation and `source.analyze` grant no history permission.
These new tools require matching development core/plugin candidates and are not
advertised as available in an existing published package. The existing delivery path supports opt-in
status/run/resume for an existing
delivery request selected by the operator with `--delivery-request`. Clients
cannot choose operational paths, credentials or keys. Existing per-operation
grants remain required; delivery uses the shared coordinator and may mutate
registry/proof state.

This optional Apizr plugin runs in its own Python environment. Use the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile)
to choose the matching catalog profile and verified target artifacts. The
[release record](https://apizr.outerspace.sh/releases/0.4.4/) describes the
functionality and validation for **Apizr 0.4.4**.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Development
locks, activations and permissions are not migrated automatically.

## Registry installation (0.4.5 candidate)

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

The repository's `server.json` describes the future 0.4.5 listing. Registry
publication is separate from package publication; neither is performed by this
candidate. The prepared MCPB wrapper uses the same explicit inputs and admission
checks for later Smithery submission; no hosted endpoint or implicit delivery is
introduced. Use published 0.4.4 core/plugin versions together until release.

See the [plugin guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/).
Python 3.11–3.14. GPL-3.0-or-later; the full license is included.
