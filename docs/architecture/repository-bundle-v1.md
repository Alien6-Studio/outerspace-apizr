<span id="repository-exposure-bundle-v1"></span>

# Repository Exposure Bundle

Repository bundles turn an explicitly validated Exposure Plan into one direct
REST server or one direct MCP server with multiple selected capabilities.
The independent contracts are `apizr.repository-interface/v1`,
`apizr.repository-rest/v1`, and `apizr.repository-mcp/v1`.
The existing single-source `apizr.rest/v1` and `apizr.mcp/v1` remain unchanged.

```text
One discovery → Catalog + Graph + retained bytes → Repository Readiness
    → Exposure Policy / Exposure Plan → Repository Interface → REST or MCP
```

## Evidence and generation boundary

```python
from apizr.repository_interfaces.generator import render_repository_bundle

artifacts = render_repository_bundle(
    catalog,
    graph,
    readiness,
    exposure_policy,
    exposure_plan,
    sources,
    interface="mcp",
)
```

The renderer validates the Exposure Plan using `validate_plan`, verifies the
complete inspected Catalog source mapping by exact keys, size and SHA256, and
requires the requested interface and `direct` compatibility for every selection.
An empty plan is valid evidence, but building a server from it is refused.
There is no backend preference, fallback or policy widening.

`analyze_repository` returns noncanonical `RepositoryEvidence` with an immutable
source mapping. `graph_repository` keeps its original Catalog/Graph return
contract. CLI discovery reads source once; all subsequent stages consume those
same bytes, including when a file changes after discovery.

Generation groups exact selected IDs by Inspection, enforces the shared validated
repository eligibility decision, and uses the same invocation-contract lowering
primitive as the single-source planner. The single-source planner still requires
local eligibility. It does not inspect or parse project source again. Existing
validation recomputes readiness conclusions **from bound artifacts**, and shared
type lowering parses declared **annotation expressions**; neither operation
reanalyzes source. Project code is never imported/executed, nor are environment
packages, Docker, Git, build backends, network or installers queried.

## Bundled sources and public surface

All inspected Catalog Python sources are bundled. `observed_support_modules`
is not a dependency closure. Bundled code is distinct from exposed capabilities:
a helper, unselected function or entire module can be included without becoming
an endpoint or Tool. Scanner source roots and exclusions control what is copied;
there is no additional bundle selection language.

Logical `shop.pricing` maps to `source/shop/pricing.py`; a real `shop` package
marker maps to `source/shop/__init__.py`. Manifests retain original relative path,
logical module, bundle path, digest, size and package marker. Namespace parents
have no fabricated source files. Contradictory trees such as `a.py` and `a/b.py`
are refused across the complete bundled universe, since that universe must be
representable for subsequent lazy imports.

Public names are permanently module-qualified: `shop.pricing.calculate`.
REST uses `/capabilities/shop.pricing.calculate`. MCP uses the qualified name
when accepted by the existing naming helper; otherwise it uses its full SHA256
fallback. Both check collisions. Input schemas, parameter kinds/defaults and
sync/async contracts come from the shared planner. Return annotations remain
informational. REST retains its existing JSON encoding behavior; MCP accepts
only finite JSON values without coercion. Failures return generic transport
errors without source exception text or traceback logging.

## Integrity and trusted execution

Bundles include canonical Catalog, Graph, Readiness, Exposure Policy and Plan,
plus the repository interface document. A manifest hashes every emitted artifact
except itself. Entry points pin the repository interface digest. Startup verifies
artifact hashes and evidence/source/public-surface linkages before project import.
These hashes establish consistency with reviewed evidence, not publisher identity
or authenticity against replacement of the entire bundle.

A shared meta-path finder owns the declared local namespace. Every actual module
load reads the bundled source, verifies size/digest, compiles those exact bytes
and executes that code object; it never delegates to an unchecked sibling loader
or a cached `.pyc`. Real initializers and relative imports follow this same path.
Synthetic namespace parents contain no source code. Already-loaded conflicting
namespaces are refused; undeclared children cannot escape into ordinary filesystem
imports. External names outside the managed namespace use normal Python resolution.
Application resources other than Python source are not packaged by v1.

Only selected modules and the modules they import execute. Unrelated sources are
hash-checked without executing them. Startup fails if any selected binding cannot
be loaded. Imports are cached by Python; module state and mutable defaults persist
between calls in this **trusted, direct** server process. No process/container
isolation is claimed. An explicit execution policy adds the independently versioned
[governed repository runtime](governed-repository-runtime.md), with a fresh local
process or OCI container per invocation. Direct behavior remains unchanged.

## Local imports and private implementation support

A selected capability may use a uniquely resolved local import when the bound
[Repository Readiness refinement](repository-readiness-v1.md#resolved-local-import-refinement)
proves its binding and module initialization evidence. The source-local report
still records `APIZR-READY-015`; repository eligibility does not forge an Inspection
or set its local `can_generate_interface` to true. REST and MCP use the same
repository decision and the same pure signature/type lowering as single-source
generation. External, dynamic, ambiguous or otherwise unproven imports stay blocked.

Selecting `facade.calculate` packages its `helper.py` support but does not create
a route or Tool for `helper.double`. Required helpers need coherent bindings and
execution evidence, not their own public JSON input contract. See the
[user example](../getting-started/user-guide/exposure.md#use-private-helpers-from-the-same-repository).
The upcoming 0.4.5 builder revalidates the Exposure Plan through the single
[selected-evidence authority](exposure-plan-v1.md#complete-evidence-and-fail-closed-behavior).
Required calls, references, imports and package initialization must be proven;
unrelated path diagnostics remain visible in the bundled full audit. The complete
inspected source universe is still copied and integrity-checked. The loader remains
lazy: file presence never causes an import or public route. Contradictory namespace
trees block the whole manifest. There is no source minimization, transitive effect
inference or runtime safety claim.

The current bundle fixture includes a pure private callable in its nonempty
package initializer so that retained Readiness can prove initialization. This
changes full-audit/source/manifest digests, while public REST routes and MCP Tools
remain unchanged. Initializers without sufficient facts are still refused.

## Artifacts, output and verification

REST emits `app.py`, `openapi.json`, `apizr-repository-rest.json`; MCP emits
`server.py`, `mcp-tools.json`, `apizr-repository-mcp.json`. Both include
`apizr_repository_runtime.py`, the existing shared invocation runtime,
`repository-interface.json`, evidence JSON, exact `source/` files and reviewed
transport requirements. Application dependencies remain the operator's explicit
runtime/deployment responsibility; names are not converted into pip requirements.

The writer stages a complete bundle under the output parent, then publishes it
with an atomic directory rename. Nonempty outputs, symlinks and traversal are
refused. A failed write cleans its staging directory; no partial bundle is
published. Concurrent nonempty output cannot be overwritten.

Schemas: [interface](../specs/apizr-repository-interface-v1.schema.json),
[REST](../specs/apizr-repository-rest-v1.schema.json),
[MCP](../specs/apizr-repository-mcp-v1.schema.json).
Golden manifests/OpenAPI/Tools are checked across Python 3.11–3.14 and relocation.
Tests cover exact source/evidence binding, invocation parity, qualified names,
non-execution audit hooks, trusted REST/MCP transports, source tampering, package
semantics, state, refusals and transactional output. The package has its own 90%
branch-coverage floor and strict type checking.
