# Assess repository exposure evidence

Repository readiness evaluates existing static evidence under a declared policy.
It is **not a runtime guarantee or an authorization to give an agent access**.

Save matching Catalog and Graph artifacts from an unchanged repository:

```sh
apizr scan ./project --catalog > catalog.json
apizr graph ./project --graph > graph.json
apizr repository-readiness catalog.json graph.json
apizr repository-readiness catalog.json graph.json --format json > readiness.json
```

Use the same source-root and scan policy options for the first two commands. If
source or policy changes between them, readiness rejects their digest mismatch.
The assessment command reads only the saved JSON artifacts, never project source.

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
    "modes": ["local-process", "oci-container"],
    "require_controls": ["network_deny", "filesystem_sandbox"]
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
is unsupported by both existing modes. No runtime or container is started.

Exit status: `0` means every assessed declaration is ready and the Catalog/Graph
have no blocking completeness issue (an empty successful inventory also returns
zero); `1` means at least one declaration is non-ready or upstream inventory/Graph
is incomplete; `2` means invalid/inaccessible input, policy, or artifact linkage.
Check counts and upstream diagnostics before interpreting an empty report.

See the [v1 contract](../../architecture/repository-readiness-v1.md) for precise
state semantics, diagnostic scope mapping and policy defaults.
