# Apizr MCP plugin

Let an MCP client inspect your Python project and review recorded experiments.
Analysis reads your source without running its functions.

<!-- mcp-name: io.github.Alien6-Studio/outerspace-apizr -->

Use **Apizr 0.4.6** with the matching plugin version. Follow the
[installation guide](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile),
then [connect your MCP client](https://apizr.outerspace.sh/reference/apizr-mcp-server/#registry-installation).

You choose the project, its access policy and a separate directory for plugins.
The client needs all three paths. Install and enable the plugin before starting
the `outerspace-apizr-mcp` launcher.

Reading experiment history requires `history.read` permission. Delivery is
optional and requires its own permissions; enabling analysis does not enable it.
See the [MCP guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/)
for tools, configuration and delivery options.

Python 3.11–3.15 · GPL-3.0-or-later ·
[Release notes](https://github.com/Alien6-Studio/outerspace-apizr/releases)
