---
title: Editor engine contract
description: Versioned, read-only JSON operations shared by editors and experiment-history MCP tools in 0.4.6 development.
---

# Read engine evidence from an editor

The **0.4.6 development engine** provides `apizr editor`: one JSON request on
stdin, closed with EOF, and one JSON response on stdout. It uses the installed
engine and never embeds an engine in the client. This contract prepares editor
integrations; it does not claim the VS Code extension is already released.

Start with discovery, without selecting or opening a project:

```sh
printf '%s' '{"schema_version":"apizr.editor/v1","request_id":"discover","operation":"capabilities"}' | apizr editor
```

Check the returned protocol and supported operations before sending another
request. An unsupported protocol is refused explicitly. `engine_version` comes
from the installed distribution; protocol support is determined by discovery,
not by guessing from a package version. The provider descriptors currently
describe the built-in source recognizer; external-provider selection is separate.

| Operation | Arguments | Canonical result | Required permissions |
| --- | --- | --- | --- |
| `capabilities` | `{}` | `apizr.editor-capabilities/v1` | None |
| `inspect` | `source`, optional `module_name` | `apizr.experiment-inspection/v1` | `source.analyze` |
| `experiment_list` | Optional `status`, `source`, `capability`, `limit` | `apizr.experiment-history/v1` or `/v2` | `source.analyze`, `experiments.read` |
| `experiment_show` | `run_id` | `apizr.experiment-record/v1` or `/v2` | `source.analyze`, `experiments.read` |
| `experiment_diff` | `run_a`, `run_b` | `apizr.experiment-diff/v1` or `/v2` | `source.analyze`, `experiments.read` |
| `plan_exposure` | Optional explicit `policy` | `apizr.exposure-plan/v1` | `source.analyze` |

Results reuse the existing evidence contracts. The client renders observations
and uncertainty; it does not validate store records, reconstruct producer facts,
compute differences or infer scientific causality in another language.

## Select the project and authority at process startup

All project operations require an operator-selected absolute `--project` path and
an explicit `--operator-policy`. Requests cannot select a root, store, credentials
or permissions. Use the existing [project configuration](../getting-started/onboarding.md)
and [operator policy](operator-policy.md). To read the default history, add this
grant alongside the project's exact `source.analyze` grant:

```json
{
  "adapter": "experiments",
  "operation": "history.read",
  "target": {"kind": "local", "root": "/absolute/project"},
  "store": ".apizr/experiments/v1",
  "permissions": ["experiments.read"]
}
```

`apizr editor --store RELATIVE_STORE` selects a different store at startup and
requires a grant with that exact relative store. No directory is created by
reading. Symlinks and path traversal are refused. The captured project inode and
source authorization are rechecked around each operation. A history grant gives
no execution, provider activation, generation or publication rights.

For example, send `{"operation":"inspect","arguments":{"source":"model.py"}}`
to `apizr editor --project /absolute/project/apizr.toml --operator-policy /absolute/operator.json`.
Inspection reads the saved script or notebook, bounded input evidence and
root-level environment specifications through the existing inspection operation.
The configured source roots, excluded directories, depth and source byte limits
also apply; an editor request cannot enlarge them.
Notebook inspection requires the engine's notebook extra. It never executes cells.

## Response and diagnostics

`apizr.editor-response/v1` echoes `request_id` and `operation`, and returns `ok`,
the canonical `value` or null, plus structured diagnostics with `code`, `message`,
`severity` and optional `location`. Locations reuse `source`, one-based `line`,
zero-based `column`, and, when known, zero-based `cell_index`/`code_cell_index`
with one-based `cell_line`. The inspection's complete locations remain in `value`.
Exposure refusals also retain the canonical `exposure_diagnostics`.

Exit status is 0 for a successful response and 2 for a refusal. Invalid bodies,
duplicate keys and unknown fields are refused without echoing raw input or a
traceback. Requests are limited to 65,536 bytes and responses to 4,194,304 bytes.
Oversized results produce `response_too_large`; they are never silently truncated.
Close stdin after the request; clients own process cancellation and deadlines.

History list/show/diff use the existing complete bounded-store validation before
returning evidence, including records beyond a display filter or limit.
Diff resolves both identities in one complete traversal, sharing admitted values
only for that request. It does not use a persistent index or a targeted check.
Producer and capture values come from retained Runs; reading never imports the producing
provider. Missing, ambiguous and corrupt records produce explicit diagnostics.
No operation runs code, retrains a model, changes evidence or generates a service.

Schemas: [request](../specs/apizr-editor-request-v1.schema.json),
[response](../specs/apizr-editor-response-v1.schema.json),
[capabilities](../specs/apizr-editor-capabilities-v1.schema.json).
Reusable accepted/rejected requests and expected response fixtures live in
[`tests/fixtures/editor-contracts/conformance.json`](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.6/tests/fixtures/editor-contracts/conformance.json).
The conformance suite checks the same fixtures against JSON Schema and Python,
then compares actual stdio responses and history with the engine/CLI results.

The MCP tools `apizr_experiment_list`, `apizr_experiment_show` and
`apizr_experiment_diff` use the same argument models and history dispatch. See
[the MCP server](apizr-mcp-server.md) for its separate managed plugin startup.
