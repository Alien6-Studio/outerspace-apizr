# Exposure Plan v1

The original backend contract described here is unchanged. The 0.3 development
line also provides an opt-in [strict OCI subprocess-deny profile](subprocess-deny.md)
with a separate worker protocol; v1 static adapters retain their original guarantees.


**Development line: 0.3.0 (`0.3.0.dev0`). Latest stable: 0.2.1.**
This feature is not part of the published 0.2.1 package.

An exposure plan records an explicit publication decision over static evidence; it is not an authorization grant or runtime safety proof.

```text
Catalog → Graph → Repository Readiness
                          ↓
                   Exposure Policy
                          ↓
                    Exposure Plan
                          ↓
           Direct repository REST/MCP bundle
```

## Independent contracts and pure boundary

`apizr.exposure-policy/v1` and `apizr.exposure-plan/v1` are new independent
contracts. Breaking selection/planning semantics require new contract versions.
Existing Catalog, Graph, Repository Readiness, IR, Inspection, interface and
execution contracts retain their existing semantics and bytes.

```python
from apizr.exposure import ExposurePolicy, plan_exposure, plan_bytes, plan_digest

policy = ExposurePolicy.model_validate(
    {
        "selection": {"include": ["python:shop:calculate"]},
        "interfaces": ["rest", "mcp"],
        "execution": {"allowed": ["local-process", "oci-container"]},
    }
)
plan = plan_exposure(catalog, graph, readiness, policy=policy)
canonical = plan_bytes(plan)
identity = plan_digest(plan)
```

The API takes already validated Catalog, Graph, RepositoryReadinessReport and
ExposurePolicy models. It revalidates nested models, including unchecked copies,
and verifies the readiness report against its original evidence using the
existing pure `validate_report` boundary. There is no scan, source parsing,
filesystem access, project import/execution, network, Git, installation, build
backend, Docker invocation, environment probe or interface generator call.

## Selection and eligibility

The policy requires nonempty `interfaces` and `execution.allowed` sets. There
are no implicit interface targets or backend choices. `selection` defaults to
empty: an empty plan is valid and the human report warns that nothing is planned.

- `selection.include`: exact `python:module:symbol` IDs only.
- `selection.include_all_ready`: defaults to `false`; when explicitly `true`,
  unions all repository `READY` IDs with the explicit includes. It never adds
  `CONDITIONAL` IDs, even when conditional exposure is enabled.
- `selection.exclude`: removes IDs after all inclusions. Exclusion always wins.
- Unknown IDs in either include or exclude produce blocking diagnostics, even
  when the same unknown ID occurs in both sets. Bare names and malformed IDs
  are policy errors. No fuzzy matching or module selectors exist in v1.
- `eligibility.allow_conditional`: defaults to `false`. Explicitly selected
  `CONDITIONAL` records require `true`. `AMBIGUOUS` and `UNSUPPORTED` never pass.

REST and MCP compatibility is represented separately. Both v1 adapters consume
`local_readiness.can_generate_interface`, the authoritative shared Interface
Contract eligibility fact. Exposure never lowers or reinterprets Python types.
A conditional repository assessment can pass only if local interface eligibility
still holds (for example, unknown required effect evidence). The opt-in cannot
bypass an unresolved local callable/type contract. All requested targets must
pass; there is no partial interface selection.

## Execution composition

`execution.allowed` is an order-independent set of `direct`, `local-process`,
and/or `oci-container`. `execution.require` reuses the Repository Readiness
control vocabulary, including time/input/output bounds, environment, working
directory, network/filesystem restrictions and OCI resource limits.

For every selected capability, the plan records the sorted intersection of:

1. compatible modes in the bound Repository Readiness report;
2. explicitly allowed exposure modes satisfying exposure controls through the
   existing readiness `execution_compatibility` adapter.

There is no duplicated backend capability table or ranking. Readiness restrictions
cannot be widened. The default readiness policy considers local-process and OCI;
planning direct mode also requires a readiness policy that includes direct.
An empty compatible intersection blocks the whole requested plan. Requiring
`subprocess_deny` always blocks affected selections; PID limits do not satisfy
that requirement ([#49](https://github.com/Alien6-Studio/outerspace-apizr/issues/49)).
An empty selection has no affected capability and remains valid.

“Contract-compatible” does not mean runtime-available. The plan has no worker
image, environment values, secrets, user identities, permissions or runtime
configuration. Runtime binding belongs to the bundle/runtime stage.

## Complete evidence and fail-closed behavior

Readiness v1 expresses completeness through `graph_complete` and
`catalog_exit_code`, rather than a new `complete` field. Exposure requires
`graph_complete = true` and `catalog_exit_code = 0`, even for empty selections.
It does not require the report's aggregate exit code to be zero: unrelated
conditional/unsupported capabilities need not be selected.

`ExposureRefused.diagnostics` contains deterministic typed reasons for incomplete
evidence, unknown IDs, ineligible state, incompatible interface or execution.
The API returns no plan if any blocking diagnostic exists. Invalid models or
mismatched evidence raise `ValueError`. No partial planning policy exists in v1.
`validate_plan` recomputes the expected plan from bound evidence/policy and checks
all snapshots; structural schema validation alone is not evidence verification.

## Snapshot and dependency boundary

Each record retains its capability ID, module, repository-relative POSIX source
path, readiness state/reasons, requested and compatible interfaces, compatible
execution modes, effect snapshot and relationship evidence. Graph diagnostics,
import declarations, module import context and direct relationships retain
uncertainty without repair or effect propagation. Full input documents and
callee readiness/effect documents are not embedded.

`calls_capability`, `references_capability` and `imports_capability` are evidence
only: selecting A that calls B does not expose B. `observed_support_modules`
contains the selected source modules and known direct target modules. It is not
recursive or a complete runtime dependency closure. `external_modules` contains
lexical external module names from the selected evidence; no standard-library,
third-party, installed or vulnerability classification is attempted.

Queries: `plan.capability_ids()`, `plan.for_interface("mcp")`, and
`plan.compatible_with("oci-container")` return deterministic tuples.

## Identity and serialization

Validation checks `graph.catalog_digest == catalog_digest(catalog)`,
`graph.repository_digest == catalog.repository_digest`, and the readiness
catalog/graph/repository digests and conclusions. The plan binds:

- `repository_digest`;
- `catalog_digest`;
- `graph_digest`;
- `repository_readiness_digest` (which also binds readiness policy);
- `exposure_policy_digest`.

`policy_bytes`/`policy_digest` and `plan_bytes`/`plan_digest` use sorted JSON keys,
compact separators, UTF-8, finite values and exactly one trailing LF. Set-like
selectors, exclusions, interfaces, modes and controls are sorted and deduplicated.
There is no timestamp, checkout path, Git identity or self-digest. Relocation
preserves bytes. Unselected source changes in the scanned universe change bound
evidence and thus the plan digest; selected capability IDs remain stable.

Schemas are generated from typed models:
[policy](../specs/apizr-exposure-policy-v1.schema.json) and
[plan](../specs/apizr-exposure-plan-v1.schema.json).
The golden under `tests/fixtures/exposure/v1` selects two capabilities, retains a
call to an unexposed helper and lexical `typing` evidence, and leaves conditional,
unsupported and unrelated declarations unexposed. Tests compare committed bytes
and schemas on every supported Python version, and exercise selection order,
relocation, strictness, digest mutations, tampering and audit-hook non-execution.

## CLI and future scope

See the [exposure guide](../getting-started/user-guide/exposure.md). The CLI uses
one `analyze_repository` discovery for Catalog and Graph, assesses readiness once,
then calls the pure planner. Verification recomputes readiness conclusions from
those artifacts without rediscovery or source parsing.

[#87](https://github.com/Alien6-Studio/outerspace-apizr/issues/87) covers planning.
[#88](https://github.com/Alien6-Studio/outerspace-apizr/issues/88) adds the
[direct repository bundle stage](repository-bundle-v1.md) through `expose build`.
Governed repository execution remains deferred to
[#90](https://github.com/Alien6-Studio/outerspace-apizr/issues/90). There is no
`expose serve`, RBAC, approval service or dependency-stack split. Existing issues
[#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28),
[#49](https://github.com/Alien6-Studio/outerspace-apizr/issues/49) and
[#63](https://github.com/Alien6-Studio/outerspace-apizr/issues/63) remain open.
