# Code organization (0.4.5 development)

## Accepted package composition rule

This rule governs new code and the ongoing 0.4.5 migration. Organize by domain
responsibility. A domain owns its models, policy and operations; transports and
optional providers consume those contracts. Do not introduce a global `models/`,
`services/`, `utils/`, `helpers/` or `common/` collection.

Each Python package has one declared owner and exactly one composition role in
`architecture/packages.toml`:

| Role | Allowed composition | Example |
| --- | --- | --- |
| Domain leaf | Cohesive implementation modules; no child Python packages | `plugins/lock`, `workspace`, `repository_views` |
| Composition | Declared subdomains, exports, explicit entrypoints and named shared adapter support; no business implementation in its initializer | `plugins`, `generators`, `cli` |
| Historical | Existing generation pipeline, explicitly inventoried; no precedent for new layout | `modules`, `extensions` |
| Compatibility facade | Exact forwarding shape to one canonical implementation; no business code | `project.py`, `local_plugins/` |

The package name answers **what responsibility lives here**. Its module names
answer **which part of that responsibility lives here**, such as `models.py`,
`policy.py`, `operations.py`, `serialization.py`, `planner.py` or `worker.py`.
These are roles, not mandatory empty files. Keep a small cohesive domain together;
file counts and line counts alone do not justify another directory.

Create a child package when it has a distinct contract, dependency boundary or
lifecycle that can be named and explained. Convert the parent from domain leaf to
composition and declare both responsibilities in the inventory. For example,
`plugins/lock` owns lock validation; `plugins/local` owns installation and
activation. A new provider belongs beside the other providers rather than inside
lock validation. Do not split one responsibility just to create symmetry.

Initializers expose the owned API or remain lazy namespaces. Only the CLI
composition initializer has declared dispatch functions (`main`, `_main`);
argument parsing lives in `cli/commands`. Importing composition namespaces must
not read project configuration, discover or activate plugins, or import optional
SDKs. Cross-domain callers use the owning package's supported contracts, never
compatibility paths or private implementation helpers.

Before adding code, identify its owner, role, dependencies and import/resource
compatibility requirements. Adding a domain requires an inventory entry and an
explanation of its boundary in review. New root implementation files and new
migration exceptions are prohibited.

## Current migration state

CLI adapters and plugin management have canonical namespaces. Project declarations,
operator preferences, bounded file access and explicit workflow composition form
the `workspace` domain. Shared source/interface/delivery values live in `contracts`;
interpreter requirements live in `environment`.
Static compiler domains and execution contracts remain explicit packages. Optional
plugin distributions live outside the core package.

```text
src/apizr/
├── cli/
│   ├── __init__.py            command dispatch and Python/console entrypoint
│   ├── __main__.py            python -m apizr.cli
│   ├── commands/              argument parsing and result presentation, including inspect
│   ├── completion.py          bounded, static shell completion
│   └── completion_spec.py     captured CLI grammar
├── plugins/
│   ├── artifacts/             manifest identity, wheels and admitted requirements
│   ├── preparation/           resolve a native target, retain wheels, normalize hashes
│   ├── local/                 install, activate, invoke and uninstall
│   ├── lock/                  portable locks and artifact validation
│   ├── catalog/               explicit metadata and profile resolution
│   ├── sync/                  additive installation from a project lock
│   └── update/                locked replacement and explicit activation
├── workspace/
│   ├── project.py             explicit project declarations
│   ├── user.py                explicit operator preferences
│   ├── files.py               bounded regular-file access
│   ├── operator_policy.py     explicit operator grants
│   ├── source_access.py       authorized source admission
│   ├── compiler.py            orchestration over retained evidence
│   ├── application_resources.py  explicit application resource capture
│   └── analysis_session.py, mcp_session.py  captured session authority
├── contracts/                whole shared source/interface/delivery modules
├── environment/              interpreter targets and optional extra requirements
├── legacy/                   historical app, parser, configuration and prompts
├── capabilities/             source-local capability IR
├── repository/               bounded discovery and complete Catalog
├── graph/                    imports, bindings and dependency evidence
├── readiness/                conservative source-local assessment
├── repository_readiness/     repository evidence assessment
├── repository_views/         pure bounded projections of complete evidence
├── experiments/              intended experiment controls and observed-run evidence
├── exposure/                 explicit selection and required-evidence planning
├── interfaces/               shared interface contracts and runtime validation
├── repository_interfaces/    retained multi-source bundles
├── generators/               REST and business MCP rendering
├── execution/                governed single-capability local worker contracts
├── oci/                      single-capability OCI provider
├── repository_execution/     retained-repository local/OCI worker contracts
├── subprocess_guard/         restrictions installed before project imports
├── governed*/                REST/MCP adapters for those execution contracts
└── modules/, extensions/     historical generation pipeline

plugins/{mcp,oci,attest}/      separately packaged optional distributions
```

The root also retains compatibility facades such as `plugins_cli.py` and
`local_plugins/`. Their implementations are in the namespaces above. `root_debt` is empty: all 26 remaining root implementations have moved as whole
modules. Existing public paths remain exact forwarding facades. Functions and
classes retain their bodies; no definitions are extracted or combined.

The existing source reader in `governed.embedding` maps four moved source paths to
their installed locations. Autonomous runtimes keep their reviewed logical imports
and generated bytes. `[embedded_imports]` lists the exact imports retained in those
source modules; other internal callers use the new owning namespaces. No source
snapshot, import hook or new runtime composition mechanism is introduced.

## Required dependency direction

CLI commands parse input, call operations and present results. Core operations
and plugin management must not import CLI adapters. `workspace/compiler.py` remains usable
without importing CLI commands or optional REST/MCP/notebook dependencies.

Bounded file access (`workspace.files`) has no Apizr domain dependencies. Workspace
configuration and plugin management have no optional SDK or plugin-distribution
dependencies. Project loading reads only the explicit project file and grants no
operator authority.

Plugin management depends on core policy, project declarations, locks and the
bounded extension protocol. It does not import optional plugin distributions,
REST frameworks or the MCP SDK. Importing `apizr.plugins` performs no discovery,
installation or activation.

The allowed plugin sibling graph is acyclic and explicit. `artifacts` imports no
plugin sibling. Local installation consumes verified artifact contracts. Portable
locks and catalogs reuse those same verifiers; the optional installed-state check
in `lock` also reads `local` records. Sync consumes locks and local installation;
update consumes sync, locks and local installation. Preparation consumes artifact
verification and the existing lock target contract; it does not depend on the
local store. Its optional PyPA extra supplies ordered native wheel tags. Reverse dependencies are
prohibited.

The canonical ownership map is:

| Responsibility | Owning implementation |
| --- | --- |
| Distribution names, versions and digests | `contracts/distribution.py`, shared with delivery contracts |
| Plugin manifest identity and artifact errors | `plugins/artifacts/models.py` |
| Bounded verified HTTPS wheel transfer | `plugins/artifacts/_download_worker.py`, supervised by its caller |
| Bounded wheel bytes, digests and metadata | `plugins/artifacts/wheel.py` |
| Strict single-hash requirements, retained wheel snapshots and distribution metadata verification | `plugins/artifacts/requirements.py` |
| Native target resolution, multi-hash evidence, compatible wheel selection and atomic prepared profiles | `plugins/preparation` |
| Preparation CLI arguments and outcome presentation | `cli/commands/plugin_preparation.py` |
| Portable project locks and target compatibility | `plugins/lock` |
| Versioned catalog metadata and offline profile export | `plugins/catalog` |
| Installation, local store, explicit activation, invocation and uninstall | `plugins/local` |
| Additive installation from portable locks | `plugins/sync` |
| Locked replacement and conditional activation | `plugins/update` |

Artifact verification previously lived in `plugins/local/wheel.py` and
`plugins/local/locking.py`. Those whole modules now belong to `artifacts`, so
verification can be imported without importing installation or activation.
`Manifest` and `PluginError` have the same single definitions, re-exported from
the old local model module. Installation and inventory records remain local.
The old wheel and locking modules forward directly to the new modules, preserving
module identity and patched validation bounds. The strict installer lock remains
one SHA-256 per exact distribution pin.

The plugin lifecycle follows these dependencies:

```text
CLI → preparation → artifacts + lock target contract
CLI → catalog     → artifacts + lock
CLI → local       → artifacts
CLI → lock        → artifacts + local (optional installed-state check)
CLI → sync        → artifacts + lock + local
CLI → update      → artifacts + lock + local + sync

requested plugin → preparation → retained wheelhouse + normalized lock
                                 ↓
                     local installation → explicit activation → invocation
```

The optional `apizr_mcp`, `apizr_oci` and `apizr_attest` packages consume core APIs.
They remain independent distributions with their own installed environments.
Core `apizr.plugins` is the management layer for those distributions.

## Analysis, exposure and execution

The compiler pipeline keeps these responsibilities separate:

1. Discovery, capability analysis and Graph construction retain complete source
   evidence without executing project code.
2. Readiness assesses that evidence. `repository_views` projects it without
   replacing canonical artifacts or introducing another dependency resolver.
3. Exposure selects exact public capabilities and their required evidence.
   Interface generation consumes the retained selection and contracts.
4. Execution workers import approved project code only after integrity checks
   and the applicable restrictions. Governed adapters present REST/MCP surfaces.

Execution package variants represent different contracts:

| Contract | Worker/provider | Governed interface |
| --- | --- | --- |
| One source capability, local process | `execution` | `governed` |
| One source capability, OCI | `oci` over the shared worker | `governed_oci` |
| Retained multi-source repository, local or OCI | `repository_execution` | `governed_repository` |

Keep these identities explicit when changing workers, policies or generated
bundles. Their similar file names do not make their source authority, protocol
or deployment semantics interchangeable.

## Experiment evidence

`experiments` is a domain leaf with an independent evidence lifecycle, separate
from shared transport/build/publication primitives in `contracts`.
`model.py` owns strict Plan/Run values and evidence semantics; `values.py` owns
bounded, deeply immutable recursive JSON; `serialization.py` owns canonical
bytes, content digests and explicit Run-to-Plan validation. `__init__.py` exports
this public API. `inputs.py` owns source-only input recognition, explicit selection
and bounded local fingerprinting; it uses the existing `workspace.files` descriptor
primitive without importing workspace configuration or compilation. There is no
historical experiment facade. `randomness.py` owns bounded source-only randomness
controls and explicit distribution candidates; `environment.py` owns selected
trusted-runtime facts and static/runtime root-level specification identities.
Both source producers share the internal `_lexical.py` authority and AST bounds.
`metrics.py` owns explicit metric construction and static sklearn call signals;
`outputs.py` owns explicit output selections, static joblib candidates and current
byte observations. `_files.py` owns the one internal regular-file digest primitive
shared by input, environment and output capture. It returns factual identity or a
safety failure; callers assign their context-specific evidence provenance.

`parameters.py` adds bounded direct literal candidates using the existing
`Parameter` value. `inspection.py` composes these producers and canonical compiler
evidence; `inspection_model.py` binds their identities and derives section states.
`notebook_source.py` provides a transient cell sidecar verified against the unchanged
exporter's AST. `_locations.py` observes same-domain discovery hooks for provenance;
it adds no input/control recognition rules. `reporting.py` presents bounded text
and deterministic JSON. CLI parsing remains in `cli/commands/experiment.py`.

`planning.py` derives immutable intent from Inspection. `bindings.py` correlates
existing metric signals with conservative direct global bindings; it does not add
framework recognition. `run_protocol.py` owns bounded JSON workload messages.
`runner.py` orchestrates explicit trusted execution, using the unchanged
`execution.supervisor.kill_group` primitive for group termination and reaping.
`worker.py` executes exact inspected bytes and captures runtime facts in the child.
`store.py` publishes canonical Plan/Run bytes exclusively and validates local
history. `history.py` owns list/show queries and their intended/observed views.
These modules belong to the same evidence lifecycle; neither inspection nor its
producers import the runner, worker, protocol or history. CLI dispatch is lazy.

An Experiment Plan describes intended experiment inputs and controls. An Experiment Run records observed execution evidence. Neither proves scientific causality or reproducibility.

The dependency gate permits only experiment siblings, the existing `ValueModel`
and logical-module primitive, distribution names/digests, canonical JSON,
bounded descriptor access in `workspace.files`, standard-library modules and the
existing Pydantic typing runtime. The inspection orchestrator alone may compose
canonical capability/readiness and repository evidence plus the existing lazy
notebook adapter. Its model may reuse the corresponding canonical value contracts.
The runner alone may import the existing notebook adapter and public process-group
supervisor primitive. Runner and worker may reuse the bounded frame primitives
from `execution.protocol`, with separate experiment workload contracts.
These are explicit per-module dependency exceptions; producers and Plan/Run retain
the primitive boundary. CLI, exposure planning and data-science SDKs remain outside
it. Repository enrichment calls the existing readiness view,
whose selection-scoped evidence semantics remain authoritative.
The local store is neither a remote tracker nor an artifact repository. See
[Experiment evidence v1](experiment-evidence-v1.md) for origins, identities and
producer obligations.

## Canonical imports and compatibility

For core maintenance, use:

```python
from apizr.workspace.project import load_project
from apizr.workspace.user import load_user_config
from apizr.cli.commands.plugins import main
from apizr.plugins.local import install_extension, run_extension
from apizr.plugins.lock import create_lock, check_lock
from apizr.plugins.catalog import load_catalog, resolve_profile
from apizr.plugins.sync import sync_plugins
from apizr.plugins.update import update_plugin
```

The following previous paths remain supported:

| Previous path | Implementation |
| --- | --- |
| `apizr.<name>_cli` | `apizr.cli.commands.<name>` |
| `apizr.completion`, `apizr.completion_spec` | corresponding `apizr.cli` modules |
| `apizr.project`, `apizr.user_config`, `apizr.config_files` | `apizr.workspace.project`, `.user`, `.files` |
| `apizr.local_plugins` | `apizr.plugins.local` |
| `apizr.plugin_lock` | `apizr.plugins.lock` |
| `apizr.plugin_catalog` | `apizr.plugins.catalog` |
| `apizr.plugin_sync` | `apizr.plugins.sync` |
| `apizr.plugin_update` | `apizr.plugins.update` |

Submodule aliases share the actual implementation module, preserving class and
exception identity and visibility of patched helpers. Package facades expose
the same public objects and delegate access to loaded submodules. They contain
no duplicated business implementation or global import hook.

The console entrypoint stays `apizr.cli:main`, and `python -m apizr.cli` remains
supported. CLI arguments, completion grammar, package versions, dependencies,
canonical JSON and generated business runtime contracts are unchanged.

## Maintaining the boundaries

Run the structural gate directly:

```sh
python3 scripts/check_package_architecture.py
```

It runs in pre-commit and the CI quality job. It checks every Python package
against the ownership inventory, rejects undeclared folders and root modules,
prevents adding children to a leaf without explicit recomposition, checks
composition initializers and snake_case module names, and validates the complete
AST of each historical forwarding facade. A `Compatibility` docstring never
exempts code from checks.

Dependency checks resolve absolute imports, relative imports, `from apizr import`
and literal dynamic imports, including imports inside functions and type-checking
blocks. They reject implementation imports of historical aliases, domain-to-CLI
imports, management-to-optional-adapter imports, forbidden plugin sibling edges
and domain dependencies from bounded file access. Computed dynamic imports and
semantic cohesion still require review; the gate is not a complete Python call
or import graph analyzer.

`tests/test_folder_composition.py` deliberately misplaces code and verifies
rejection. `tests/test_package_architecture.py` separately protects installed old
imports, module identity and lazy namespace imports. CLI parsers remain covered
by the captured grammar test. Passing compatibility tests alone does not establish
that a domain composition is appropriate.

The remaining root debt and historical pipelines are recorded explicitly. Runtime
source embedding in `governed*/embedding.py` and generator resource reads must
keep using real implementation sources, never compatibility facade source text.
Keep the three execution contract identities separate during any later migration.

Coverage gates and security mutation targets follow the moved implementations.
Their existing thresholds and mutations are preserved. Continue to run
installed-wheel and isolated plugin proofs: source-tree imports alone cannot
qualify a package layout change.
