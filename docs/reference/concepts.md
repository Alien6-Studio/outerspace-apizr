# Concepts and limits

These definitions are shared by the guides. An observed result and a static
claim have different meanings; keep their evidence together when reviewing work.

| Term | Meaning | Does not establish |
| --- | --- | --- |
| Capability | A discovered top-level Python function with a logical ID | Availability of a running service |
| Inspection | Source evidence without executing the workload | Metric values or successful execution |
| Readiness | Eligibility under the selected static policy | Trust, authorization or runtime safety |
| Exposure | Explicit selection of public functions and interfaces | Deployment or helper publication |
| Bundle | Generated adapter, contracts and retained source/files | A started server or signed provenance |
| Experiment Plan | Intended source, inputs and controls | What execution actually observed |
| Experiment Run | Recorded execution outcome and selected facts | Scientific causality or reproducibility |
| Diff | Comparison of two validated Run records | An explanation of why a metric changed |
| Delivery | Build/transfer/proof observations bound to exact identities | Organizational deployment approval |

## Two uses of MCP

The **Apizr analysis MCP plugin** provides `apizr_analyze`, `apizr_readiness` and
`apizr_plan_exposure`. Its default workflow reads repository evidence; optional
delivery tools require explicit configuration and separate authority.
A **generated business MCP server** provides your selected functions, such as
`api.quote`. Calling that tool executes your code. Both can be consumed by Python
clients; a paid assistant is optional.

## Four environments

The core CLI, each installed extension, the scientific workload and the generated
service may have separate interpreters. Installing an extra supplies dependencies
for its declared workflow; installing a plugin creates its own locked environment.
Neither operation installs libraries into an existing notebook kernel or service.

Installation stores reviewed bytes. Activation chooses an installed plugin version.
Authorization grants an exact operation/target. These are independent decisions.

## Supported interfaces

Top-level sync/async functions and supported JSON-shaped inputs can generate
REST/MCP. Primitive types, supported containers/unions/literals and bounded stdlib
class-form TypedDict inputs are described in [readiness](../architecture/capability-readiness-v1.md).
Arbitrary classes, decorated/rebound functions, streams and unresolved contracts
remain subject to the exact refusal rules. Return annotations describe results;
they are not runtime type enforcement.

## Execution boundaries

Direct services import trusted code in the transport process and retain globals.
Governed local calls use a fresh process with bounds, environment controls and
process cleanup, while retaining host filesystem/network access. OCI execution
adds the documented Linux container controls and requires a prepared worker image.
The service-image OCI plugin packages a direct service; it is a separate operation
from the governed per-call OCI worker.

Local experiment history holds JSON evidence and output identities, not model
bytes, shared tracking or a backup system. See [evidence retention](../operations-guide/evidence.md).
Trunx and other platforms apply their own authenticated approval/deployment
mechanisms to the [existing exported documents](external-governance.md).
