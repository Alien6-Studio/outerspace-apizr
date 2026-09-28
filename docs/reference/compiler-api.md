# Call the repository compiler from Python

!!! warning "0.4 development — not released"

    Stable is 0.3.0. Use the [candidate installation](../getting-started/install.md#evaluate-the-040-candidate)
    for this page's 0.4 commands; they are not available in stable 0.3.0.
    The [development setup](../development/0.4.md#install-a-development-wheel)
    is for contributors building their own evaluation wheels.

`apizr.compiler` provides the orchestration used by `apizr readiness`,
`apizr expose plan` and `apizr expose build rest|mcp`. It requires only the base
installation. It does not discover plugins or import optional transport servers.

## Example

Given `repository/sample.py` containing
`def add(a: int, b: int = 1) -> int: return a + b`, run this Python code from its
parent directory. The output directories must be absent or empty.
First prepare `operator-local.json` using the complete [local grant](operator-policy.md#authorize-repository-analysis), with the canonical absolute path of `repository`.
The installed-wheel smoke test executes this exact example outside the checkout.

```python
from pathlib import Path

from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy
from apizr.operator_policy import load_operator_policy
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy

operator = load_operator_policy(Path("operator-local.json"))
prepared = prepare_exposure(
    Path("repository"),
    operator_policy=operator,
    readiness_policy=RepositoryReadinessPolicy.model_validate(
        {"execution": {"modes": ["direct"]}}
    ),
    policy=ExposurePolicy.model_validate(
        {
            "selection": {"include": ["python:sample:add"]},
            "interfaces": ["rest", "mcp"],
            "execution": {"allowed": ["direct"]},
        }
    ),
)
report, plan = prepared.readiness, prepared.plan
rest = render_bundle(prepared, interface="rest")
mcp = render_bundle(prepared, interface="mcp")
write_bundle(Path("python-rest"), rest)
write_bundle(Path("python-mcp"), mcp)
```

Analysis runs once. Both renderings use the retained source bytes even if the
repository changes afterward. Rendering returns a `dict[str, bytes]` without
writing files or starting a server. `write_bundle` is the existing staged writer:
it checks paths, refuses symlinks and nonempty destinations, and publishes the
complete bundle without replacing existing contents.

## Operations and contracts

| Operation | Parameters | Result |
| --- | --- | --- |
| `assess_readiness(root, *, operator_policy=None, scan_policy=None, graph_policy=None, readiness_policy=None)` | `str` or `Path`, existing `ScanPolicy`, `GraphPolicy`, `RepositoryReadinessPolicy` | Existing `RepositoryReadinessReport`, including diagnostics and `exit_code` |
| `prepare_exposure(root, *, policy, operator_policy=None, scan_policy=None, graph_policy=None, readiness_policy=None)` | Same analysis policies plus an explicit `ExposurePolicy` | `PreparedExposure` retaining evidence, readiness, policy and plan |
| `render_bundle(prepared, *, interface, execution_policy=None, runtime_image=None)` | Prepared context, `"rest"` or `"mcp"`, existing execution policy/image models | Existing bundle filenames and bytes |

`PreparedExposure` is an in-memory container for existing contracts, not a new
serialized schema. Its `evidence` is the existing `RepositoryEvidence` with
`catalog`, `graph` and retained `sources`. Canonical serializers remain
`report_bytes`, `plan_bytes`, `catalog_bytes` and `graph_bytes` in their existing
packages. For already saved Catalog/Graph artifacts, continue to use
`apizr.repository_readiness.assess_repository`; the repository-first operation
intentionally performs discovery.

Readiness alone needs no exposure selection. To reuse analysis for a plan and
bundles, call `prepare_exposure` once and use its `readiness` result; do not call
`assess_readiness` first unless you intend a separate discovery. Default readiness
still permits local-process/OCI contracts, so the example explicitly requests
direct readiness as well as direct exposure. Policies remain independent; the
compiler does not merge them or widen the selected execution modes.

Optional `scan_policy` and `graph_policy` retain their existing bounds. CLI
`--exclude-dir` adds to the default exclusions; a Python `ScanPolicy` with
`excluded_directories` explicitly supplied replaces that field, so include
`ScanPolicy().excluded_directories` when you want the same additive behavior.

## Errors and execution boundaries

Operations do not print or exit the process. Invalid policy/input validation
raises the existing `ValueError` subclasses (including Pydantic
`ValidationError`); filesystem and decoding errors propagate. Exposure selection
raises `ExposureRefused` with structured `diagnostics`. Rendering preserves
`BundleRefused` and `PolicyRefused`. Readiness can return a report with nonzero
`exit_code`; callers decide how to handle it. The CLI retains its existing error
messages and exit-code translation.

Explicit selection is required for a nonempty bundle. An empty selection can
produce an empty plan but cannot produce a bundle. Ineligible or unknown selected
capabilities are refused. No source imports, package builds or project execution
occur during analysis, planning or rendering.

Omitting `execution_policy` selects direct generation; `ExecutionPolicy` selects
local-process and `ExecutionPolicyV2` selects OCI with an explicit `RuntimeImage`.
The chosen backend must be allowed by the plan: there is no fallback. These
operations preserve existing boundaries and do not start/probe backends, pull
images, resolve remote Git repositories or publish services. Runtime optional
dependencies are needed when running the generated service, not when rendering.
See [exposure policies](../getting-started/user-guide/exposure.md) for the three
independent policy roles and existing limitations.

## Source admission in development 0.4

`operator_policy` is an explicitly loaded `OperatorPolicy`. Omission raises
`AuthorizationDenied` with a fixed structured decision. Filesystem `scan`,
`discover`, `analyze_repository` and `graph_repository` share this gate. Local
roots match canonical absolute paths; relative arguments resolve against the
caller's working directory. No path component may be a symlink. Git analysis
accepts its live `GitSnapshot`, bound to the actual acquisition and commit.
See [Git acquisition](git-sources.md#python-api).

Admission does not authorize exposure, execution, image build, signing or
publication. Existing contracts, selection refusals and bounds remain. Primitives
accepting already supplied bytes/artifacts do not read a root and remain outside
this gate. Arbitrary Python execution is not an authorization sandbox. Stable
0.3.0 instructions retain their historical syntax.
