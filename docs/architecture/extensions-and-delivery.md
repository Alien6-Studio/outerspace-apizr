---
description: Separate optional plugin lifecycle, service-image packaging, governed OCI workers and delivery proof identities.
---

# Extensions and service delivery

Trace how optional providers turn a reviewed bundle into an image and a
verifiable handover. The result is a delivery design that preserves the
distinction between installed tools, operation authority and deployment approval.

Read [Request and execution boundaries](execution-boundaries.md) first. The
[verifiable service example](../examples/verified-delivery.md) supplies the
complete disposable registry and optional Attest exercise.

## Installation, activation and authority are separate

Core plugin management stores and validates reviewed extension bytes in a
separate environment. Activation selects an installed version. The operator
policy authorizes managed build, registry publication and signing operations
for an exact target before the core launches the extension or accesses its
operational credentials. These managed operations are the path shown below.

<div class="apizr-diagram" tabindex="0" role="region" aria-label="Extension lifecycle and authority diagram" markdown="1">

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
---
flowchart TB
    accTitle: Optional extension lifecycle and operation authority
    accDescr: Reviewed wheels and locks lead to installation and explicit activation. An operation request separately passes an operator grant check. Only an active compatible installation and an authorized operation can enter the bounded extension runtime and optional provider process.
    Wheels["Reviewed wheels and lock"] --> Installed["Installed extension environment"]
    Installed --> Active["Explicitly activated version"]
    Request["Managed delivery operation + target"] --> Grant["Operator grant check"]
    Active --> Runtime["Core extension runtime"]
    Grant --> Runtime
    Runtime --> Plugin["Optional provider process"]
```

</div>

The diagram's two inputs to the runtime are both required. An installed plugin
does not grant access to an arbitrary repository, registry, signing key or
destination. A project plugin declaration is a reproducible installation input,
not an operator permission. Verification and other operations keep their own
documented requirements. The low-level extension API invokes an explicitly
trusted program without managed installation identity or operator authorization;
it does not install, discover or activate plugins.

| Optional provider | Responsibility | Detailed interface |
| --- | --- | --- |
| `outerspace-apizr-mcp` | Serve authorized repository analysis; optionally configured delivery tools | [Analysis MCP server](../reference/apizr-mcp-server.md) |
| `outerspace-apizr-oci` | Prepare/build a service image and verify its registry transfer | [OCI service images](../reference/oci-service-plugin.md) |
| `outerspace-apizr-attest` | Sign, timestamp and verify the documented delivery proof | [Attest delivery proofs](../reference/attest-delivery-plugin.md) |

The modern [extension invocation protocol](../reference/extension-invocation.md)
is separate from [historical pipeline plugins](../getting-started/developer-guide/plugins.md).
The [extension guide](../developer-guide/extensions.md) demonstrates a minimal
modern provider without modifying Apizr's own core domains.

## A service image is not a per-call worker image

<div class="apizr-diagram" tabindex="0" role="region" aria-label="Service image and governed worker image diagram" markdown="1">

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
---
flowchart TB
    accTitle: Two distinct uses of OCI images
    accDescr: The OCI service plugin packages a direct REST or MCP bundle into a service image, which can be delivered to a registry and run as a persistent service. Governed OCI invocation instead needs an explicitly prepared compatible worker image and creates a fresh container for each call.
    Bundle["Direct REST / MCP bundle + application inputs"] --> Plugin["OCI service plugin build"]
    Plugin --> Service["Persistent service image"]
    Service --> Registry["Verified registry delivery"]
    Service --> App["Transport and function in service container"]
    Worker["Prepared governed worker image"] --> Fresh["Fresh container per invocation"]
    Fresh --> Call["Selected function under execution policy"]
```

</div>

Building a service image does not enable governed per-call OCI execution.
The service plugin packages a direct bundle, transport requirements and
explicit application inputs. A governed worker image implements the required
execution protocol and contains its own prepared application dependencies.
Use [Operations → execution](../operations-guide/execution.md) to choose the
invocation boundary and [Operations → delivery](../operations-guide/delivery.md)
to package and transfer a service.

## Follow the planned and observed identities

<div class="apizr-diagram" tabindex="0" role="region" aria-label="Delivery identity chain diagram" markdown="1">

```mermaid
---
config:
  flowchart:
    useMaxWidth: false
---
flowchart TB
    accTitle: Bundle, build, push and optional proof identity chain
    accDescr: A verified bundle, inspected wheel closure and build target form a DeliveryPlan. The build produces an observed immutable image and DeliveryManifest. Registry transfer produces a PushResult. Optional Attest signing creates a receipt that is checked against independent public trust and retained delivery records.
    Inputs["Verified bundle + wheels + build target"] --> Plan["DeliveryPlan: intended build identity"]
    Plan --> Build["Build and inspect immutable image"]
    Build --> Manifest["DeliveryManifest: observed image and platform"]
    Manifest --> Push["PushResult: observed registry transfer"]
    Push -.-> Proof["Optional receipt + retained proof files"]
    Trust["Independent public trust"] --> Verification["Offline proof verification"]
    Proof --> Verification
    Verification --> Handover["Verified delivery evidence for handover"]
```

</div>

The [DeliveryPlan](delivery-identities.md) binds validated upstream compiler
evidence, bundle artifacts, application inputs, inspected wheel identities and
build target. It contains intended inputs, not an observed image, destination
or receipt. The **DeliveryManifest** binds that Plan to observed image ID,
platform and build-input identity. Changing a destination does not change the
manifest of an already built image.

The **PushResult** records the separately verified transfer. Optional Attest
proofs bind the documented build/push observations and manifest to a signed,
timestamped receipt. Offline verification uses retained public proof files and
independently configured public trust; it does not require a private key or
contact the registry.

Verification authenticates the recorded evidence and its links. It does not
repeat source analysis, rerun the build, inspect a live image or prove that
Attest supervised the build. A valid receipt does not establish model quality,
scientific validity or organizational permission to deploy.

## Finish with the appropriate handover

Review the immutable image reference, platform, observed transfer and any
required verified proof. [Proof-required admission](../reference/delivery-admission.md)
has its own explicit requirements and separately authorized final promotion.
[Multi-destination delivery](../reference/multi-destination-delivery.md) retains
independent outcomes and can explicitly resume delivery of one immutable build.

External platforms apply their own authenticated approval and deployment
mechanisms to the [exported documents](../reference/external-governance.md).
Apizr does not supply an organizational approval console or a native rollback
command. The [Operations guide](../operations-guide/index.md) provides the
procedures; the contract sections in this architecture guide provide exact
schemas, bindings and limits.
