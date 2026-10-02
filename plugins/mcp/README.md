# outerspace-apizr-mcp

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
[release record](https://apizr.outerspace.sh/releases/0.4.3/) describes the
functionality and validation for **Apizr 0.4.3**.

Installation does not activate a plugin or authorize its operations. Enable the
chosen version explicitly and supply the required operator policy. Development
locks, activations and permissions are not migrated automatically.

## Registry launcher (0.4.3)

The new `outerspace-apizr-mcp` command delegates to `apizr mcp serve`. Supply
`--project /absolute/project/apizr.toml`,
`--operator-policy /absolute/operator.json` and
`--plugins-dir /absolute/plugins`. Install and activate the matching MCP plugin
in that separate store first. Installing this launcher through a registry client
does not install or activate the governed plugin, grant access to a project, or
enable delivery. Startup retains the existing admission checks and isolated
plugin interpreter. No hosted endpoint is provided.

The released 0.4.2 wheel does not include this console command. The repository's
`server.json` describes the 0.4.3 listing. Registry publication is separate from
package publication. Use `apizr mcp serve` with published 0.4.2 installations.

See the [plugin guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/).
Python 3.11–3.14. GPL-3.0-or-later; the full license is included.
