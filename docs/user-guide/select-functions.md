# Choose which functions are public

Share a calculation while keeping training and implementation helpers private.
The result is a bundle whose HTTP routes or MCP tools match your explicit choice.

## Before you begin

Install the core using [Install Apizr](../getting-started/install.md). Use the
[downloadable quote project](../examples/business-quote.md) if you need files.
Inspect your source before executing it. For a repository, prepare a
`source.analyze` grant for its exact root, as shown in the example.

## Choose an interface and a function

A capability ID has the form `python:module:symbol`. With `src` as the source
root, `src/shop/api.py` defining `quote` gives `python:shop.api:quote`.
Use the ID displayed by `apizr scan`; do not guess it from the package name.

Write a readiness policy that permits direct execution, and an exposure policy
containing only the public entry points. The quote example's selection is:

```json
{
  "selection": {"include": ["python:api:quote"]},
  "interfaces": ["rest", "mcp"],
  "execution": {"allowed": ["direct"]}
}
```

`READY` describes eligibility; selection determines publication. Avoid `--all-ready`
when you intend one public function. Exclusions must name existing IDs too: a typo
fails instead of silently leaving a function public.

## Build and verify your selection

Run the [quote example's complete commands](../examples/business-quote.md).
Open `openapi.json` and check that the only business path is
`/capabilities/api.quote`. In `mcp-tools.json`, check that only `api.quote` appears.
`/health` and `/docs` are infrastructure routes, not private helper exposure.

The multi-module bundle retains the entire inspected Python source universe.
`inventory.product` and `pricing.tax` are implementation support, not public tools.
Choose bounded source roots/exclusions to avoid including unrelated files you do
not want to distribute; private API visibility does not mean source secrecy.

## Share without an experiment

Use `apizr expose build rest` or `mcp` for a repository, or `apizr generate rest`
or `mcp --select` for a single source. These workflows take existing functions
directly. There is no training or history prerequisite.

If you choose to use a successful Run, [experiment exposure](../getting-started/user-guide/experiment-exposure.md)
also checks source and explicitly selected resource identities. Changed files
require a legitimate new Run or restoration of the reviewed exact bytes.

## When a function is refused

Inspect the diagnostic and its required dependency path. Correct the source or
supply a supported contract; do not neutralize safeguards. An unrelated experiment
can remain unfinished, but an ambiguous helper required by your selected function
still blocks it. Try [the research scenario](../examples/research-serving.md).

Continue with [REST](../getting-started/user-guide/rest.md),
[MCP](../getting-started/user-guide/mcp.md), or the
[exposure reference](../getting-started/user-guide/exposure.md).
