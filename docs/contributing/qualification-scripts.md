---
title: Qualification scripts
description: Ownership, callsites, retained evidence and stable entry points for repository qualification.
---

# Qualification scripts

`architecture/scripts.toml` inventories every source file under `scripts/`.
Each entry declares its owner, role, qualified gate/journey, direct workflow/job
callers, retained job evidence and whether CI reaches it. Helpers inherit the
evidence of their calling jobs; resource entries describe inputs rather than
claiming to emit reports. Evidence paths are caller-selected templates from
artifact steps, alongside stdout/stderr. They are not a complete dynamic call
graph or a claim that each helper writes every file retained by its job.

Implementations are grouped by responsibility:

| Package | Responsibility |
| --- | --- |
| `scripts.qualification.ci` | Repository policy, dependencies, architecture, coverage, security and CI measurements |
| `scripts.qualification.examples` | Product README and frozen executable journey fixtures against installed candidate wheels |
| `scripts.qualification.packaging` | Coordinated candidates, installed distributions, Homebrew and release evidence |
| `scripts.qualification.extensions` | Plugin preparation, catalogues, profiles, synchronization and cleanup |
| `scripts.qualification.interfaces` | MCP clients, schemas, REST collections and onboarding |
| `scripts.qualification.experiments` | Scientific contracts, SDK capture, notebooks, history and installed journeys |
| `scripts.qualification.delivery` | Operator authority, artifact/image delivery, Attest receipts and admission |
| `scripts.qualification.repository` | Git acquisition, SSH/HTTPS and source provenance |
| `scripts.qualification.fixtures` | Disposable protocol, signing, registry and isolation fixtures |
| `scripts.mcp_distribution` | Existing named helpers for official MCP distribution and index verification |
| `scripts/client_collection_tools` | Exact native vendor manifests and compatibility tooling |

The root Python commands remain supported, for example
`python scripts/check_package_architecture.py`. They contain only a checked
dispatch shape and forward to one implementation. Internal Python imports use
the canonical package, and development workflows normally use module entry
points from the checkout root:

```sh
uv run --locked python -m scripts.qualification.ci.check_script_architecture
uv run --locked python -m scripts.qualification.ci.check_package_architecture
```

Some installed-interpreter calls deliberately retain the stable CLI path.
Standalone probes run the actual file without adding checkout directories to
`sys.path`, preserving `python -I` and copied/source-free driver behavior.
Their inventory entries declare `source_free`; they cannot import repository
qualification helpers. Keep copied proof files self-contained and copy the
implementation rather than its dispatcher. Historical release evidence and
external Action/GitLab commands retain their existing root CLI names.

For a new proof, choose the package that owns the journey and a descriptive
`*_proof.py` or `smoke_*.py` name. Role values are `smoke`, `proof`, `check`,
`prepare`, `release`, `fixture` and `tool`. Add the inventory entry with its gate
and callsites in the same change. Namespace initializers only compose; shared
helpers belong in a named responsibility package, never `utils`, `helpers`,
`common` or `services`. Do not add new root implementations or copy proof logic
into a compatibility command.

The ownership gate rejects missing/stale files, absent workflow script/module
targets, stale callsites/evidence, misplaced implementations, executable
namespace initializers, business logic in dispatchers, compatibility imports
inside implementations and checkout imports in source-free probes. Generated
Python caches and the vendor tool's installed `node_modules` are excluded; their
tracked manifests and compatibility check remain inventoried. The gate runs in
pre-commit and the CI quality job. Pyright's existing recursive `scripts` include
covers canonical packages and compatibility commands together.

The initial reference audit found one script without a workflow, documentation
or other-script caller: `completion_model.py`. It is retained as a documented
developer tool because it regenerates the captured modern CLI grammar used by
completion conformance tests. After reviewing a deliberate CLI grammar change,
regenerate the snapshot with:

```sh
uv run --locked python -m scripts.qualification.ci.completion_model
```

Review the resulting `src/apizr/cli/completion_spec.py` diff with the CLI change.
This command is a development operation, not part of normal qualification.

Implement related tickets locally, use focused checks while the batch evolves,
then push and qualify the whole batch once. Moving a proof or adding a ticket
does not require starting another full platform matrix in the middle of that
batch. The separate pytest performance comparison is manual only.

Website build and publication tools live under `scripts/` in the separate
`gh-pages` checkout; they are outside the product ownership inventory. Academy
source/shot-list preparation runs there with
`python3 academy/academy_lessons.py --output /absolute/new/directory`.
This command prepares lesson inputs; it does not render or publish videos.
The loopback-only
`python3 -m scripts.qualification.interfaces.telemetry_conformance --endpoint http://127.0.0.1:8080 --output /absolute/report.json`
checks a disposable receiver against the public synthetic corpus. It never
qualifies production hosting, storage or retention.

The engine performance baseline is also manual only. Its
`scripts.qualification.experiments.benchmark_engine` command records import,
inspection, SDK, file digest, publication, history and editor timings, with
function-call profiles. See [the measurement method and budgets](../architecture/engine-performance.md).
