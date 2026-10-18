# Choose execution controls

Select where trusted Python functions execute and check that the requested
controls can be enforced. The generated interface stays the same; runtime
behavior and prerequisites change.

## Before you begin

Start from a working direct bundle and reviewed code. Core analysis/generation is
static. Direct startup and function invocation execute trusted code. Local workers
require POSIX process facilities; OCI workers also require Docker and a prepared
trusted image with the relevant worker protocol labels.

| Choice | State between calls | Available boundary | Main limit |
| --- | --- | --- | --- |
| Direct | Persists in server | Existing transport process | No process timeout or filesystem/network isolation |
| Local process | Fresh worker each call | Time/JSON bounds, clean or explicit environment, process-group cleanup | Host filesystem/network accessible; detached descendants outside group cleanup |
| OCI container | Fresh container each call | Documented Linux network/filesystem/resource controls | Trust daemon/kernel/image; no VM or hostile-code guarantee |
| Experiment Run | Fresh workload process | Recorded outcome and selected observations | Host access; no experiment Docker runner |

## Configure a local worker explicitly

For one source, create `execution.json` containing `{}`. Pass it to
`apizr generate rest` or `mcp --execution-policy execution.json` using the source
and new output directory from the single-source guide.
For repository generation, readiness and exposure must both permit
`local-process`; passing an execution policy does not widen them.

A local policy requesting network deny, filesystem sandbox or subprocess deny is
refused before launch. Do not describe a fresh directory as a filesystem sandbox.
The [execution reference](../getting-started/user-guide/execute.md) gives exact
single-capability invocation and policy vocabulary.

## Prepare OCI separately

Use the [worker-image procedure](../getting-started/user-guide/execute.md#advanced-explicit-oci-container-execution)
and retain its immutable image ID and platform. V2 execution policy chooses
`oci-container`; repository bundles require a repository-aware worker image.
Generation never pulls the image. Missing controls/images fail without fallback.
The strict subprocess-deny profile also prohibits new threads; assess workload
compatibility before selecting it.

## Keep service images distinct

The optional OCI service plugin builds an image containing a direct REST/MCP
service. That image is different from a governed per-call worker image.
Run-bound application resources currently support direct service bundles and
their OCI service images; governed per-call resource packaging remains refused.

See [governed repository execution](../architecture/governed-repository-runtime.md)
for exact integrity checks and runtime failures. Continue with
[image delivery](delivery.md) if a direct service image meets your needs.
