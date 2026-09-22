# Repository / Agent Readiness v1

The original backend contract described here is unchanged. The 0.3 candidate
line also provides an opt-in [strict OCI subprocess-deny profile](subprocess-deny.md)
with a separate worker protocol; v1 static adapters retain their original guarantees.


Repository readiness means **sufficient static evidence under this versioned policy**.
It is not a runtime guarantee, security certification, AI safety score, probability,
LLM judgment, recommendation, or authorization to give an agent access.

The independent contracts are `apizr.repository-readiness-policy/v1` and
`apizr.repository-readiness/v1`. They consume Catalog v1, Graph v1 and embedded
local Readiness v1 without changing any of those contracts. Local Readiness remains
authoritative for interface eligibility.

```python
from apizr.repository_readiness import RepositoryReadinessPolicy, assess_repository

report = assess_repository(catalog, graph, policy=RepositoryReadinessPolicy())
```

This call performs no filesystem discovery, source parsing, AST analysis, import
resolution, readiness rerun, source execution, or Docker availability check. It
roundtrips both typed documents and the policy through validation, including nested
unchecked model copies, and requires:

- `graph.catalog_digest == catalog_digest(catalog)`;
- `graph.repository_digest == catalog.repository_digest`;
- graph capability metadata, module identities and catalog exit evidence agree
  with the Catalog.

The report binds the repository, catalog, graph and readiness-policy digests. It
introduces no separate source identity. Digests bind content; they do not authenticate
who supplied it or prove that declared evidence is true. `validate_report(report,
catalog, graph)` re-evaluates and compares every conclusion and snapshot against
its bound inputs. Parsing a standalone report validates its internal invariants;
use `validate_report` when the original artifacts are available.

## Assessment universe and state

There is one assessment for every embedded per-source Readiness assessment,
including declarations rejected from IR. Its original `capability_id` is unchanged.
`local_readiness` retains source/module/symbol/span, `in_ir`, local state,
`can_generate_interface`, all dimensions, and the original `APIZR-READY-*` reasons.
`in_catalog` explicitly indicates trusted catalog membership. Rejected declarations
have unavailable graph evidence and unknown effect facts; no replacement IDs or
capabilities are invented. Sources without inspections have no declarations to
assess: their Catalog diagnostics remain in the report.

State precedence is `ambiguous > unsupported > conditional > ready`.

| State | Repository meaning |
| --- | --- |
| `ready` | Locally interface-eligible; every supplied requirement is satisfied by static evidence and at least one declared mode supports all required controls. |
| `conditional` | Required evidence is incomplete, or local Readiness is conditional. Unknown information is not a hard failure. |
| `unsupported` | Local Readiness is unsupported, an effect required false is evidenced true, a hard interface requirement is unmet, or no declared mode supports all controls. |
| `ambiguous` | Upstream Readiness is ambiguous, or relevant Graph identity/import evidence cannot select a stable unique binding. This is never downgraded. |

`ready` does not mean every dependency executes, all behavior is known, side effects
are absent, or an agent should receive access. There is no numeric aggregate score
or blanket repository readiness state. Counts include all four states. Catalog and
Graph diagnostics/completeness remain separately visible, even for empty reports.

## Policy and effect evidence

Default policy, shown as JSON (the CLI accepts JSON):

```json
{
  "schema_version": "apizr.repository-readiness-policy/v1",
  "effects": {"require_known": [], "require_false": []},
  "relationships": {"require_resolved": true},
  "execution": {
    "modes": ["local-process", "oci-container"],
    "require_controls": []
  },
  "require_interface": false
}
```

Local interface eligibility **always** gates `ready`. `require_interface: true`
additionally makes present ineligibility a hard policy failure, so an upstream
conditional interface yields repository `unsupported`. Its default is false to
preserve the distinction between incomplete evidence and proven local lack of
support. Unknown options, effect/control names and coercible boolean strings are
rejected; set-like policy lists are deduplicated and sorted.

Effects come only from Capability IR embedded in source Inspections. Every effect
retains its `value` and `evidence`: `filesystem_read`, `filesystem_write`, `network`,
`environment`, `subprocess`, `state_mutation`, `secrets`, `external_service`.
The current source analyzer generally leaves effects unknown. A declaration that
has no IR contributes unknown effects, never false by absence.

| Requirement | Unknown | True | False |
| --- | --- | --- | --- |
| `require_known` | conditional | satisfied as known | satisfied as known |
| `require_false` | conditional | unsupported | satisfied |

For example, `{"require_known": ["network", "filesystem_write"],
"require_false": ["secrets"]}` requires three explicit facts. A backend network
control does not turn unknown network effect evidence into false. When both effect
lists name one effect, both requirements apply and one unknown reason is retained.

## Graph evidence and exact diagnostic mapping

Each in-Catalog declaration has a `resolved`, `partial`, or `unavailable`
relationship dimension. Graph v1 is the only source of relationships.

- Diagnostics match the declaration's source path. A diagnostic inside its inclusive
  local Readiness source span affects that declaration. A diagnostic inside another
  declaration's span does not affect it.
- Diagnostics outside every Readiness declaration span in that module, or without
  a line, affect all declarations in the module. This conservatively represents
  module binding/import uncertainty. Graph v1 has no diagnostic scope field; no
  new lexical analysis is performed.
- A global Graph resource-limit diagnostic (`path == "."`) affects all declarations
  because Graph v1 discards every syntax relationship on aggregate exhaustion.
- Missing/unanalysed module evidence, input failure, unavailable analysis, or resource
  exhaustion yields `unavailable`. Other relevant diagnostics yield `partial`.
- Relevant import declarations with `unresolved`, `star` or `ambiguous` names also
  make the dimension partial. `APIZR-GRAPH-002` (unstable/multiple repository import
  interpretations), `APIZR-GRAPH-009` (module collision), or an ambiguous import name
  additionally preserve identity ambiguity as repository `ambiguous`.
- Dynamic/star imports, rebound imports, unstable calls and unstable callable
  references therefore remain visible. Resolved external imports are ordinary
  evidence and do not independently make relationships partial. Their separate
  local Readiness dependency reasons remain authoritative.

`relationships.require_resolved` defaults to true. Setting it false removes the
relationship completeness requirement; it does not clear local Readiness or
identity ambiguity. Overall Graph incompleteness from an unrelated module does not
change a declaration's state, but remains visible on the report and CLI exit status.

`relationships.direct` preserves outgoing capability graph edges, including
`calls_capability`, `references_capability`, `imports_capability`, and any local or
external module imports. `module_imports` separately preserves module-scope imports
as context; these are not rewritten as capability edges. `imports` retains relevant
Graph import declarations. `dependencies` snapshots the IDs, local Readiness and IR
effects of the direct capability targets in those two groups.

These snapshots are context only. A call from A to B does not cause A to inherit
B's effects or readiness. A call from B to C does not add C to A's canonical direct
relationships. Graph v1 edges describe possible direct static calls, not execution
proofs. There is no transitive effect or state propagation in v1.

## Execution compatibility: additive v1 completion

Readiness defines its own transport-neutral `Control` vocabulary; it does not
extend the control enum or alter any execution policy, plan, backend, or generated
bundle contract. The static adapter lives in `repository_readiness/execution.py`.
It obtains local guarantees from `BackendCapabilities` without calling the host
availability function. Its explicit OCI additions map to the existing reviewed
network/filesystem controls and `Resources.memory_bytes`, `cpu_millis`, and `pids`.
No runtime behavior or #58 embedded-code hash changes are involved.

Only declared control support is assessed, independently of host OS, environment,
Docker, images or daemon access. Every mode says `runtime_availability: not_assessed`.
At least one selected mode must support **all** required controls; support cannot
be assembled from multiple modes. Compatibility is not a recommendation or ranking.

| Readiness control | direct | local-process | OCI-container |
| --- | --- | --- | --- |
| `wall_timeout` | no | yes | yes |
| `input_limit` | no | yes | yes |
| `output_limit` | no | yes | yes |
| `environment` (clean/allowlisted) | no | yes | yes |
| `working_directory` (fresh) | no | yes | yes |
| `network_deny` | no | no | yes |
| `filesystem_sandbox` | no | no | yes |
| `memory_limit` (hard memory limit) | no | no | yes |
| `cpu_limit` (CPU quota) | no | no | yes |
| `pid_limit` | no | no | yes |
| `subprocess_deny` | no | no | no |

`direct` represents existing ungoverned invocation, with an empty guarantee set
and `backend_version: direct`; it does not invent a governed runtime version.
It must be explicitly selected. With no requested controls it is compatible; with
any requested control it is incompatible. The unchanged default modes remain
`local-process` and `oci-container`.

Memory, CPU and PID requirements describe support for the existing OCI policy's
configured limits. Readiness does not choose numeric limits or promise a given
allocation. Memory hard limits are distinct from CPU quotas, which constrain CPU
use rather than guaranteeing latency. PID containment does not prohibit creating
subprocesses: `subprocess_deny` remains unsupported everywhere, in this frozen static adapter.

### Byte compatibility with the original v1

Schemas only add enum values. Old policy defaults, accepted names, semantics and
canonical bytes remain unchanged. The original #59 policy/report goldens are
retained unchanged; additional snapshots capture the default policy and its report
at baseline `ebe7af7`. Tests cover all 768 combinations of the old control/mode
subsets, and revalidate saved reports against their original inputs.

To avoid changing old report bytes merely by expanding an advertised guarantee
list, `supported_controls` is a vocabulary projection:

- Policies using only original modes and controls retain the original v1 list.
- Explicit selection of `direct` or any resource control enables the completed
  vocabulary in every selected mode's list.

This affects the breadth of the reported list, not the meaning of any old control.
Compatibility always tests all requested controls against one mode's guarantees.
New capabilities are visible only when the input explicitly opts into this additive
completion; no default digest is silently changed. To inspect the full matrix in a
report, explicitly select all three modes. Old documents remain valid, and new
resource requirements are never silently ignored.

Container compatibility is conditional on actual deployment of the existing OCI
execution policy, including clean environment, network deny, constrained filesystem
and configured resource limits. Assessment does not create a plan, select an image,
establish availability or promise invocation success. Docker, its daemon, a worker
image, and the necessary Linux controls can all be absent while static compatibility
is true.

Human output lists each selected mode's compatible/incompatible result, missing
controls and the number of repository-ready declarations whose control requirements
it satisfies. This is evidence context; it does not select a backend. `--details`
adds supported controls and expands all declarations.

## Repository reason codes

Machine semantics use `code` and optional typed `effect`; messages are presentation.
Original local reason codes are retained unchanged in `local_readiness`.

| Code | Meaning |
| --- | --- |
| APIZR-REPOREADY-001 | Hard interface generation requirement unmet |
| APIZR-REPOREADY-002 | Required Graph evidence unavailable |
| APIZR-REPOREADY-003 | Required relationships partial |
| APIZR-REPOREADY-004 | Required effect unknown (`effect` names it) |
| APIZR-REPOREADY-005 | Required-false effect evidenced true (`effect` names it) |
| APIZR-REPOREADY-006 | No declared execution mode satisfies every required control |
| APIZR-REPOREADY-007 | Relevant identity/binding ambiguity |
| APIZR-REPOREADY-008 | Declaration absent from trusted Catalog |

Canonical UTF-8 JSON has sorted object keys, ordered assessments and a final newline.
`policy_bytes`, `policy_digest`, `report_bytes`, `report_digest` expose independent
content identities. Published schemas are
[policy](../specs/apizr-repository-readiness-policy-v1.schema.json) and
[report](../specs/apizr-repository-readiness-v1.schema.json).

## Repository-first orchestration

`apizr readiness ROOT` calls `graph_repository(...)` exactly once, then passes that
result's Catalog and Graph to the same `assess_repository` used by the artifact-first
CLI. The existing discovery manifest feeds both layers: source bytes are not reopened
between Catalog, Graph and readiness. The pure assessment API above is unchanged.

`--source-root`, `--exclude-dir` and all Scan/Graph bounds share parsing and policy
construction with `apizr scan` and `apizr graph`. `--policy FILE` selects the readiness
policy; `--report` and `--format json` emit the same canonical v1 report, with no
wrapper or progress output on stdout. The root path never enters canonical identity.
`--details` expands human output beyond its default 20 declarations. The existing
`apizr repository-readiness CATALOG GRAPH` remains fully supported, including its
complete human output and `--format json`; it also accepts `--report`.

Instrumentation tests count exactly one discovery and one read per source, mutate
source after Catalog assembly to detect reopening, compare independent Scan/Graph
artifacts with repo-first bytes, and check ordering/location/hash-seed invariance.
An isolated audit-hook test forbids source execution, source writes, subprocesses,
network access, Git/package-install commands and Docker/transport imports; hostile
top-level statements, decorators and defaults remain inert.
