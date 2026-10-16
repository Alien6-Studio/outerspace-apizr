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

## Legacy Python imports and generation commands

Use the [canonical owning imports](../architecture/code-organization.md#canonical-imports-and-compatibility)
and the modern `inspect` → readiness/exposure → `generate rest/mcp` workflow.
The historical `--script/--notebook` pipeline and compatibility facades are still
present in this development snapshot. Their removal within 0.4.6 is tracked by
[#284](https://github.com/Alien6-Studio/outerspace-apizr/issues/284),
[#331](https://github.com/Alien6-Studio/outerspace-apizr/issues/331) and
[#291](https://github.com/Alien6-Studio/outerspace-apizr/issues/291).
Final release instructions must reflect those completed removals before publication.

Start with the [SDK quickstart](../getting-started/tracking.md), or retain the
[ordinary notebook path](../getting-started/data-science.md) without instrumentation.
