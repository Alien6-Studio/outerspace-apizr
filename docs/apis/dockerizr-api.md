<span id="dockerizr-api"></span>

# Dockerizr API — removed in 0.4.6

The historical notebook/script pipeline and its HTTP generation service were
removed during 0.4.6 development. This URL is retained for migration. Existing
0.4.5 generated applications are independent artifacts; upgrading Apizr does not
rewrite them.

Use the [migration table](../releases/migrate-0.4.6.md#removed-generation-pipeline)
for the replacement of each CLI, Python, HTTP and plugin entrypoint. Start with
[inspection](../getting-started/user-guide/inspect.md), select public functions
explicitly, then [generate REST](../getting-started/user-guide/rest.md) or
[MCP](../getting-started/user-guide/mcp.md). For a repository, use the
[exposure workflow](../getting-started/user-guide/exposure.md).

Notebook conversion remains available through the supported
[notebook exporter](../modules/notebook-transformr.md), without executing cells.
