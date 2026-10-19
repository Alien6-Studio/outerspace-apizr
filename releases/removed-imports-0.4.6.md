# Removed Python import paths in 0.4.6

Use the canonical owner shown below. The public `apizr` console command and
`python -m apizr.cli` keep their modern arguments. This removes Python forwarding
modules and package aliases, without changing versioned evidence schemas.

The baseline had 79 facades. Six legacy app/configuration/http/main/prompt/delivery
facades were removed with the historical pipeline; this change removes the other
73 (40 root modules, 30 old plugin-management modules/packages, and three old
artifact-verification paths inside `plugins.local`). The normative compatibility
and root-debt inventories are now empty.

## Deprecation decision

Deprecation is documentation-only during 0.4.6 development, followed by removal
before publication. Import-time warnings would change lazy import behavior and
require retaining or expanding forwarding machinery just before its deletion.
The old exact-forwarding import tests passed all 75 cases before removal. Current
tests verify canonical targets, absence of retired paths, inert namespace imports
and the source closures of autonomous runtimes.

“Documented” means an explicit reference in the pre-removal checkout's docs or
examples. Other entries were historical forwarding paths without an individually
identified current example. The architecture guide also advertised whole alias
families. This inventory does not establish external usage; no external consumer
notification was requested or sent. Historical releases remain historical.

## CLI aliases

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.ci_cli` | `apizr.cli.commands.ci` | Historical forwarding path |
| `apizr.clients_cli` | `apizr.cli.commands.clients` | Historical forwarding path |
| `apizr.completion` | `apizr.cli.completion` | Documented |
| `apizr.completion_spec` | `apizr.cli.completion_spec` | Documented |
| `apizr.delivery_cli` | `apizr.cli.commands.delivery` | Historical forwarding path |
| `apizr.execute_cli` | `apizr.cli.commands.execute` | Historical forwarding path |
| `apizr.exposure_cli` | `apizr.cli.commands.exposure` | Historical forwarding path |
| `apizr.generate_cli` | `apizr.cli.commands.generate` | Historical forwarding path |
| `apizr.git_source_cli` | `apizr.cli.commands.git_source` | Historical forwarding path |
| `apizr.graph_cli` | `apizr.cli.commands.graph` | Historical forwarding path |
| `apizr.mcp_cli` | `apizr.cli.commands.mcp` | Historical forwarding path |
| `apizr.onboarding_cli` | `apizr.cli.commands.onboarding` | Historical forwarding path |
| `apizr.plugins_cli` | `apizr.cli.commands.plugins` | Historical forwarding path |
| `apizr.readiness_cli` | `apizr.cli.commands.readiness` | Historical forwarding path |
| `apizr.repository_cli` | `apizr.cli.commands.repository` | Historical forwarding path |
| `apizr.repository_readiness_cli` | `apizr.cli.commands.repository_readiness` | Historical forwarding path |
| `apizr.scan_cli` | `apizr.cli.commands.scan` | Historical forwarding path |

## Workspace and environment aliases

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.config_files` | `apizr.workspace.files` | Documented |
| `apizr.project` | `apizr.workspace.project` | Documented |
| `apizr.user_config` | `apizr.workspace.user` | Documented |
| `apizr.optional` | `apizr.environment.extras` | Historical forwarding path |
| `apizr.runtime` | `apizr.environment.python_target` | Documented |
| `apizr.analysis_session` | `apizr.workspace.analysis_session` | Historical forwarding path |
| `apizr.application_resources` | `apizr.workspace.application_resources` | Historical forwarding path |
| `apizr.compiler` | `apizr.workspace.compiler` | Documented |
| `apizr.mcp_session` | `apizr.workspace.mcp_session` | Historical forwarding path |
| `apizr.operator_policy` | `apizr.workspace.operator_policy` | Documented |
| `apizr.source_access` | `apizr.workspace.source_access` | Historical forwarding path |

## Plugin management packages

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.local_plugins` | `apizr.plugins.local` | Documented |
| `apizr.local_plugins._download_worker` | `apizr.plugins.artifacts._download_worker` | Historical forwarding path |
| `apizr.local_plugins.activation` | `apizr.plugins.local.activation` | Historical forwarding path |
| `apizr.local_plugins.backend` | `apizr.plugins.local.backend` | Historical forwarding path |
| `apizr.local_plugins.control` | `apizr.plugins.local.control` | Historical forwarding path |
| `apizr.local_plugins.download` | `apizr.plugins.local.download` | Historical forwarding path |
| `apizr.local_plugins.locking` | `apizr.plugins.artifacts.requirements` | Historical forwarding path |
| `apizr.local_plugins.models` | `apizr.plugins.local.models` | Historical forwarding path |
| `apizr.local_plugins.operations` | `apizr.plugins.local.operations` | Historical forwarding path |
| `apizr.local_plugins.retirement` | `apizr.plugins.local.retirement` | Historical forwarding path |
| `apizr.local_plugins.store` | `apizr.plugins.local.store` | Historical forwarding path |
| `apizr.local_plugins.uninstall` | `apizr.plugins.local.uninstall` | Historical forwarding path |
| `apizr.local_plugins.usage` | `apizr.plugins.local.usage` | Historical forwarding path |
| `apizr.local_plugins.wheel` | `apizr.plugins.artifacts.wheel` | Historical forwarding path |
| `apizr.plugin_catalog` | `apizr.plugins.catalog` | Documented |
| `apizr.plugin_catalog.generation` | `apizr.plugins.catalog.generation` | Historical forwarding path |
| `apizr.plugin_catalog.models` | `apizr.plugins.catalog.models` | Documented |
| `apizr.plugin_catalog.operations` | `apizr.plugins.catalog.operations` | Historical forwarding path |
| `apizr.plugin_lock` | `apizr.plugins.lock` | Documented |
| `apizr.plugin_lock.models` | `apizr.plugins.lock.models` | Historical forwarding path |
| `apizr.plugin_lock.operations` | `apizr.plugins.lock.operations` | Historical forwarding path |
| `apizr.plugin_lock.tags` | `apizr.plugins.lock.tags` | Historical forwarding path |
| `apizr.plugin_sync` | `apizr.plugins.sync` | Documented |
| `apizr.plugin_sync.models` | `apizr.plugins.sync.models` | Historical forwarding path |
| `apizr.plugin_sync.operations` | `apizr.plugins.sync.operations` | Historical forwarding path |
| `apizr.plugin_sync.preparation` | `apizr.plugins.sync.preparation` | Historical forwarding path |
| `apizr.plugin_sync.probe` | `apizr.plugins.sync.probe` | Historical forwarding path |
| `apizr.plugin_update` | `apizr.plugins.update` | Documented |
| `apizr.plugin_update.models` | `apizr.plugins.update.models` | Historical forwarding path |
| `apizr.plugin_update.operations` | `apizr.plugins.update.operations` | Historical forwarding path |

## Contract aliases

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.analysis_contracts` | `apizr.contracts.analysis` | Historical forwarding path |
| `apizr.application` | `apizr.contracts.application` | Documented |
| `apizr.bounded_json` | `apizr.contracts.json` | Historical forwarding path |
| `apizr.contract_lowering` | `apizr.contracts.lowering` | Historical forwarding path |
| `apizr.contract_types` | `apizr.contracts.types` | Historical forwarding path |
| `apizr.delivery` | `apizr.contracts.delivery` | Documented |
| `apizr.delivery_results` | `apizr.contracts.results` | Historical forwarding path |
| `apizr.distribution_identity` | `apizr.contracts.distribution` | Historical forwarding path |
| `apizr.publication_contracts` | `apizr.contracts.publication` | Historical forwarding path |

## Analysis and generation aliases

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.capability_notebooks` | `apizr.generators.notebooks` | Documented |
| `apizr.inspection` | `apizr.capabilities.inspection` | Documented |
| `apizr.output` | `apizr.interfaces.files` | Historical forwarding path |

## Plugin artifact aliases

| Removed import | Canonical owner | Reference status |
| --- | --- | --- |
| `apizr.plugins.local.wheel` | `apizr.plugins.artifacts.wheel` | Historical forwarding path |
| `apizr.plugins.local.locking` | `apizr.plugins.artifacts.requirements` | Historical forwarding path |
| `apizr.plugins.local._download_worker` | `apizr.plugins.artifacts._download_worker` | Historical forwarding path |

## Autonomous runtime imports

The source reader now reads canonical installed paths directly, with no historical
path map. Generated files use `contracts/types.py`, `contracts/lowering.py`,
`contracts/application.py` and `capabilities/inspection.py` inside `apizr_governed`.
Inspection remains the same projected model, excluding analyzer and notebook code.
Existing bundles remain self-contained; regenerating changes their runtime bytes,
artifact hashes and enclosing manifests. It does not rewrite retained evidence.

| Canonical source module with retired import | Embedded consumer and qualification |
| --- | --- |
| `capabilities/inspection.py` | Core inspection; local/OCI single-source bridges project only the Inspection definition. Recheck installed notebook/script inspection and both transport closures. |
| `contracts/lowering.py` | Local/OCI/strict single-source bridges. Regenerate REST/MCP manifests and exercise real isolated servers. |
| `execution/model.py`, `execution/planner.py` | Local/OCI/strict single-source workers. Repository bridges retain their existing narrow ExecutionResult projection. Recheck process and container invocation. |
| `interfaces/model.py`, `interfaces/planner.py`, `interfaces/schema.py` | Shared interface values/planning; local/OCI single-source closures and repository model closure. Recheck direct interface bytes, binding and structured payloads. |
| `oci/planner.py` | OCI single-source closure; repository bridges project check_controls. Recheck allow/deny container execution and manifests. |
| `readiness/model.py` | Local/OCI single-source closure and core assessments. Recheck report bytes and eligibility. |
| `repository_interfaces/model.py` | Repository local/OCI/strict closures. Recheck application declarations and real REST/MCP repository workers. |
| `subprocess_guard/single.py` | Strict single-source OCI bridge only. Recheck subprocess denial and its transport closures. |

The qualification suite covers all 16 single-source/repository × direct/local/OCI/strict
× REST/MCP modes, installed wheels, independent plugins and containers.
See the [general migration guide](migrate-0.4.6.md).
