# Migrate from 0.4.5 to the 0.4.6 development engine

0.4.6 is under development. Use retained candidate wheels and the qualified VSIX;
publication and coordinated version promotion remain separate release gates.

| Your workflow | Development behavior |
| --- | --- |
| Ordinary `experiment inspect/run` | Existing no-instrumentation commands remain available. Runs now retain selected scientific-provider provenance in their digest-bound Plan. |
| Existing v1 history | Original Plan/Run bytes and digests remain authoritative. Read, show and diff do not require an installed provider. No store rewrite or migration command is needed. |
| SDK sessions and decorators | New in-process captures use v2 evidence. Unknown source identity remains unknown; explicit logging does not infer scientific causality. |
| CLI history JSON | Lists use the v2 history view for mixed v1/v2 stores. Show retains the original record version; diff selects the appropriate view. Historical v1-only comparisons retain their canonical bytes. |
| Python history API | `list_runs` keeps its v1 default; `include_values=True` selects the enriched v2 view. `read_history` accepts both versions. |
| Static recognition | `apizr providers list` reports exact versions and limits; `--providers FILE` explicitly selects recognition. The first configured owner claims each capability even if disabled or unavailable; failure yields unknown evidence. |
| VS Code | Select a compatible installed engine explicitly and grant workspace trust plus operator permissions. The extension ships no engine and runs no analysis during activation. |
| Telemetry | Collection is off by default; opt-in enables bounded local counters only. Production transmission is unavailable. CI, serving workers and editor opt-outs override consent. |

Keep `.apizr/experiments/v1` when upgrading; this existing directory can contain
both record versions. Do not edit stored JSON to change a schema number or digest.
Corrupted, mismatched or incomplete records are refused. Back up the complete
store before any manual filesystem maintenance.

The [retained compatibility proof](https://github.com/Alien6-Studio/outerspace-apizr/tree/0.4.6/review/journey-trust-0.4.6)
uses real v1 Runs captured by 0.4.5 and canonical show/diff reference outputs
produced by the exact `v0.4.5` tagged source. It checks
Plan/Run admission, canonical show/export and diff, without producer invocation.
It does not assert that an older engine can read new v2 records.

## Removed generation pipeline

The legacy pipeline was deprecated with a `DeprecationWarning` and CLI notice
at its common FastAPI renderer before removal in the same development line.
Its separate YAML configuration, HTTP upload service, mutable step engine,
standalone generators, i18n/template resources and `legacy` extra are removed.
No input is silently routed to another generator; unknown commands exit 2.

| Removed surface | Supported migration |
| --- | --- |
| `apizr --script FILE`, `apizr --notebook FILE`; `python -m apizr.main`; `apizr.main.convert` | `apizr inspect FILE`, then `apizr generate rest FILE --select NAME --output-dir DIR` or `generate mcp`. Notebook inputs use the `notebook` extra. |
| `modules.code_analyzr.main`, `AstAnalyzr`, legacy metadata JSON | `apizr inspect FILE --ir` for typed Capability IR; `apizr scan ROOT` for an explicit repository. Legacy metadata JSON is not a Capability IR document. |
| `modules.fast_apizr.main` and its generator/model/service classes | Generate a REST/MCP bundle from reviewed source and readiness; select public capabilities explicitly. No conversion of arbitrary legacy metadata. |
| `modules.dockerizr.main` and Docker/Gunicorn/requirements generators; `--build-image` | Build a reviewed modern OCI bundle with explicit dependencies/resources and execution policy. Follow the exposure guide; image construction and delivery remain explicit separate operations. |
| `--configuration`, `--include`, `--requirements`, `--skip-*`, `--interactive`, `--lang` on the old pipeline | Use explicit `apizr.toml`, application inputs and operator/readiness/exposure/execution policies. Old YAML is not read as modern configuration. |
| `apizr.app:app`, stage ASGI apps, `/process_file/`, `/code/analyze_file/`, `/notebook/convert_notebook`, `/fastapi/get_fastapi_code/`, `/docker/*` | Use CLI generation or the explicit compiler Python API. Serve generated business bundles through their own reviewed REST/MCP runtime. No replacement public upload service is started. |
| `apizr.pipeline.v1`, `PipelinePlugin`, `Context`, `AutomationEngine`, `--plugin`, `plugin_options` | Port explicit operations to the current trusted extension protocol, or maintain a separate explicit application build step. No automatic hook activation. |
| `apizr.modules.notebook_transformr.transformr.NotebookTransformr` | `apizr.notebooks.NotebookTransformr`; configuration is `apizr.notebooks.NotebookTransformrConfiguration`. Export and formatted-script bytes are preserved. |
| `outerspace-apizr[legacy]` | Select `notebook`, `http`, `mcp`, `clients` or `preparation` for the workflow actually used. `questionary` is no longer required. |
| `apizr.configuration`, `.http`, `.app`, `.prompt`, `.legacy_delivery`, `.legacy` | Removed with their owning legacy operations; there is no forwarding stub. Use the supported workflows above. |

Existing generated applications, retained v1 history and versioned modern bundle
contracts are not rewritten. Review resulting routes and payloads when regenerating
with the modern compiler; the historical generator's output is not its contract.
The old complex-notebook YAML and pipeline-plugin examples were retired; use the
ordinary data-science notebook, SDK/Jupyter guide and independent provider example.

See [inspection](../getting-started/user-guide/inspect.md),
[exposure](../getting-started/user-guide/exposure.md),
[compiler Python API](../reference/compiler-api.md),
[notebook conversion](../modules/notebook-transformr.md) and
[plugin management](../reference/plugin-authors.md).

## Removed Python compatibility imports

The other 73 root/plugin-management facades and all embedded historical import
exceptions are removed in 0.4.6. Use the
[complete canonical replacement table](removed-imports-0.4.6.md). The console
entrypoint and modern arguments stay the same. Existing autonomous bundles remain
self-contained; newly generated governed bundles have new source paths and hashes.
Versioned evidence, public interface declarations and direct bundle bytes remain
unchanged. No compatibility import hook or warning stub is installed.

Start with the [SDK quickstart](../getting-started/tracking.md), or retain the
[ordinary notebook path](../getting-started/data-science.md) without instrumentation.
