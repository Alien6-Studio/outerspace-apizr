# Code organization (0.4.5 development)

Start with the responsibility you need to change. CLI adapters and plugin
management have their own namespaces; static compiler domains and execution
contracts remain explicit packages. Optional plugin distributions live outside
the core package.

```text
src/apizr/
├── cli/
│   ├── __init__.py            command dispatch and Python/console entrypoint
│   ├── __main__.py            python -m apizr.cli
│   ├── commands/              argument parsing and result presentation
│   ├── completion.py          bounded, static shell completion
│   └── completion_spec.py     captured CLI grammar
├── plugins/
│   ├── local/                 install, activate, invoke and uninstall
│   ├── lock/                  portable locks and artifact validation
│   ├── catalog/               explicit metadata and profile resolution
│   ├── sync/                  additive installation from a project lock
│   └── update/                locked replacement and explicit activation
├── capabilities/             source-local capability IR
├── repository/               bounded discovery and complete Catalog
├── graph/                    imports, bindings and dependency evidence
├── readiness/                conservative source-local assessment
├── repository_readiness/     repository evidence assessment
├── repository_views/         pure bounded projections of complete evidence
├── exposure/                 explicit selection and required-evidence planning
├── interfaces/               shared interface contracts and runtime validation
├── repository_interfaces/    retained multi-source bundles
├── generators/               REST and business MCP rendering
├── execution/                governed single-capability local worker contracts
├── oci/                      single-capability OCI provider
├── repository_execution/     retained-repository local/OCI worker contracts
├── subprocess_guard/         restrictions installed before project imports
├── governed*/                REST/MCP adapters for those execution contracts
├── compiler.py               Python orchestration over retained evidence
└── modules/, extensions/     historical generation pipeline

plugins/{mcp,oci,attest}/      separately packaged optional distributions
```

The root also retains compatibility facades such as `plugins_cli.py` and
`local_plugins/`. Their implementations are in the namespaces above. New core
code imports the canonical namespaces; historical callers keep their existing
imports.

## Dependency direction

CLI commands parse input, call operations and present results. Core operations
and plugin management must not import CLI adapters. `compiler.py` remains usable
without importing CLI commands or optional REST/MCP/notebook dependencies.

Plugin management depends on core policy, project declarations, locks and the
bounded extension protocol. It does not import optional plugin distributions,
REST frameworks or the MCP SDK. Importing `apizr.plugins` performs no discovery,
installation or activation.

The plugin lifecycle follows these dependencies:

```text
CLI adapters → catalog / lock / sync / update → local installation operations
                                               ↓
                                      policy and extension protocol
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

## Canonical imports and compatibility

For core maintenance, use:

```python
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

`tests/test_package_architecture.py` protects old imports, module identity, lazy
namespace imports and the direction of dependencies. Production implementations
must use canonical paths rather than importing compatibility facades. CLI
parsers remain covered by the captured grammar test.

Coverage gates and security mutation targets follow the moved implementation
files. Their existing thresholds and mutations are preserved. Continue to run
installed-wheel and isolated plugin proofs: source-tree imports alone cannot
qualify a package layout change.
