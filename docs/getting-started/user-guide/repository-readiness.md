# Assess repository exposure evidence

Repository readiness evaluates existing static evidence under a declared policy.
It is **not a runtime guarantee or an authorization to give an agent access**.

For repository-first assessment, run:

```sh
apizr readiness .
apizr readiness . --source-root src
apizr readiness . --policy policy.json --details
apizr readiness . --source-root src --report > readiness.json
```

This performs one bounded discovery shared by Scan, Catalog and Graph, then evaluates
readiness. `--report` and `--format json` emit identical canonical JSON. `--details`
expands the human report beyond 20 declarations. Repeat `--source-root` for disjoint
roots or `--exclude-dir` for additional excluded directory basenames. Bounds are
shared with Scan/Graph: `--max-file-bytes`, `--max-source-files`, `--max-total-bytes`,
`--max-entries`, `--max-depth`, `--max-ast-nodes`, `--max-relationships`, `--max-calls`
and `--max-imports`. No project modules execute, and no network, subprocess, Git,
package installer or Docker operation is invoked.

For offline evaluation or artifact pipelines, the existing artifact-first command
remains available. Save matching Catalog and Graph artifacts from an unchanged repository:

```sh
apizr scan ./project --catalog > catalog.json
apizr graph ./project --graph > graph.json
apizr repository-readiness catalog.json graph.json
apizr repository-readiness catalog.json graph.json --format json > readiness.json
```

Use the same source-root and scan policy options for the first two commands. If
source or policy changes between them, readiness rejects their digest mismatch.
The artifact-first command reads only the saved JSON artifacts, never project source.
With identical source universes and policies, both workflows produce byte-identical reports.

For a single-discovery Python workflow:

```python
from apizr.graph import graph_repository
from apizr.repository_readiness import assess_repository

artifacts = graph_repository("./project")
report = assess_repository(artifacts.catalog, artifacts.graph)
for assessment in report.assessments:
    print(assessment.capability_id, assessment.state.value)
```

Require effect evidence and execution controls with `--policy policy.json`:

```json
{
  "effects": {
    "require_known": ["network", "filesystem_write"],
    "require_false": ["secrets"]
  },
  "relationships": {"require_resolved": true},
  "execution": {
    "modes": ["direct", "local-process", "oci-container"],
    "require_controls": ["network_deny", "filesystem_sandbox", "memory_limit", "cpu_limit", "pid_limit"]
  }
}
```

The policy checks facts already present in the artifacts. Unknown effects remain
unknown; requesting a control does not establish an effect value. The existing
analyzer normally reports unknown effects, so requiring known effects will normally
produce `conditional` until evidence is supplied by the artifact producer.

Read each declaration's local readiness, additional repository reasons, direct
relationship evidence and dependency snapshots. Duplicate or otherwise rejected
declarations remain represented even when absent from the trusted Catalog. Counts
cover `ready`, `conditional`, `unsupported` and `ambiguous`; no numeric score is used.

Execution compatibility describes static backend control support, not availability.
A network-deny requirement permits the existing OCI mode; absolute subprocess deny
is unsupported by both existing modes. No runtime or container is started. `direct` declares no governed controls and is
compatible only when none are required. It is explicitly selectable and is **not**
added to the existing defaults. Each selected mode must satisfy all controls alone;
there is no preferred backend or recommendation.

Four copyable policies are provided under `examples/readiness/`:

| Policy | Requirements |
| --- | --- |
| `ungoverned.json` | All three modes explicitly selected; no governed controls required |
| `governed-local.json` | Wall timeout, clean environment and fresh working directory |
| `isolated-oci.json` | Network deny, filesystem isolation, memory, CPU and PID limits |
| `impossible.json` | Absolute subprocess deny, unsupported by every mode |

For example, from the Apizr checkout:

```sh
apizr readiness ./project --policy examples/readiness/isolated-oci.json --report
```

This is an additive v1 completion. Existing policies and report bytes remain unchanged.
Their `supported_controls` lists keep the original vocabulary projection; explicitly
selecting `direct` or a new resource control exposes the completed vocabulary. Static
compatibility still says nothing about installed runtimes or available Linux controls.

Exit status: `0` means every assessed declaration is ready and the Catalog/Graph
have no blocking completeness issue (an empty successful inventory also returns
zero); `1` means at least one declaration is non-ready or upstream inventory/Graph
is incomplete; `2` means invalid/inaccessible input, policy, or artifact linkage.
Check counts and upstream diagnostics before interpreting an empty report.

See the [v1 contract](../../architecture/repository-readiness-v1.md) for precise
state semantics, diagnostic scope mapping and policy defaults.
