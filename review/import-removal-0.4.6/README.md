# Canonical imports and autonomous runtimes — 0.4.6 development

This implements #291 on the official `0.4.6` branch. No publication, version tag,
stable-branch change or publication workflow is included. Candidate metadata
remains 0.4.5 pending coordinated promotion.

The baseline was `3533f79b3cae96b8d802bc571d04105f277571b7`. The complete old
forwarding contract passed 75 tests before removal. `inventory.json` records the
73 remaining facades, their canonical targets, groups and explicit references in
the pre-removal checkout. The six legacy facades were already removed with
#284/#331. No external consumer notification was requested or sent; this inventory
does not establish external usage.

## Deprecation and structural gate

The [complete migration table](../../releases/removed-imports-0.4.6.md)
documents deprecation followed by removal within this development line. The signal
is documentation-only: introducing import-time warnings immediately before
removal would expand forwarding machinery and alter lazy import behavior. The
public console entrypoint and modern arguments remain `apizr.cli:main` and
`python -m apizr.cli`.

All 73 forwarding modules/packages are deleted: 40 root modules, 30 plugin-management
paths and three artifact-verification aliases inside `plugins.local`. The root
contains only `__init__.py`. The normative root-debt and compatibility inventories
are empty; embedded-import exceptions and the source reader's historical path map
are gone. The package gate no longer accepts a facade AST, a migration/embedded
exception, an expanded root module list or imports of absent core modules. The
separate 107 qualification-script CLI forwarders remain outside installed code.

Canonical modules retain explicit re-exports such as the shared lowering functions
and local Manifest/PluginError identities. `implementation-shapes.json` verifies
that all 11 surviving changed production modules outside embedding retain identical
non-import ASTs. Schema literals, definitions, public interface meanings and stored
experiment evidence are not renamed or rewritten.

## Reviewed embedded layout

Generated standalone packages now use `contracts/types.py`, `contracts/lowering.py`,
`contracts/application.py` and `capabilities/inspection.py` beneath `apizr_governed`.
The existing narrow Inspection/ExecutionResult/worker projections remain, without
copying analyzers, notebook exporters, plugin management or optional SDKs. Import
closure tests cover both transports in local/OCI/strict and repository bridges.

`bundles-before.json`, `bundles-after.json` and `bundle-changes.json` retain every
artifact path and explicit `sha256` digest for 16 combinations: single-source/repository × direct/local/OCI/
subprocess-deny × REST/MCP. All four direct cases retain every byte. Governed
runtime imports/paths and enclosing manifests change; plans, public declarations
and contract versions remain unchanged. Eight current single-source/repository governed
manifest goldens are regenerated. Frozen published history and direct goldens are
untouched. Existing autonomous bundles remain self-contained.

## Installed and actual-runtime proofs

The fresh wheel/sdist pass metadata, README, license, required-resource and root
layout checks. `artifacts.json` retains their exact identities; every wheel source
file matches the checkout. The minimal installed wheel outside the checkout checks
all 73 canonical targets and refuses all retired paths. Base installation still
has exactly five dependencies. Independent clients/notebook/HTTP/MCP installations,
real HTTPS/SSH sources and notebook experiment exposure pass.

A separately installed trusted extension invokes correctly, preserves activation,
HTTPS and locked-dependency behavior, and leaves the entire core snapshot unchanged.
The same new wheel builds a disposable Linux/arm64 worker with locked core runtime
dependencies. Installed direct/local/OCI/strict repository REST/MCP, single-source
OCI execution and standalone REST/MCP from Python/notebooks run outside the checkout.
The six actual strict REST/stdio/HTTP cases cover both single-source and repository
bridges, syscall denial, tampering refusal and recovery. Worker acquisition is
explicit; these proofs do not assert production publication or all-platform kernel
qualification.

`qualification.json` retains final test, coverage, static-check and CI results.

## Qualification results

The common suite ran once in 352.51 seconds: 7,583 passed and 74 expected platform/
explicit-worker-image skips. Its four failures were the current repository
bridge/manifest goldens that still bound old runtime paths. Regeneration first
asserted every non-artifact field identical; `golden-updates.json` records only
added/removed paths and changed hashes. All 19 associated schema/bundle/golden
checks pass after this data-only refresh. The structural/dispatch set passes 168
tests. The common suite was not repeated for unchanged production code.

Combined branch-aware coverage is 97.54%, with all 22 required coverage checks
passing. All 172 security mutants are killed after a 470-test baseline. The six
actual strict transport/tamper/recovery cases pass in 21.42 seconds. Ruff, Pyright,
package/tooling architecture, pre-commit and strict 128-page HTML checks pass. The
disposable worker image was removed and no invocation container remained. CI
qualifies the exact pushed tree across the existing interpreter/platform matrix.
