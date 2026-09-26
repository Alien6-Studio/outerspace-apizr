# Technical reference

For your first project, follow [Quickstart](../getting-started/quickstart.md), then [The full journey](../getting-started/introduction.md).
Read the [Capability Compiler overview](../architecture/overview.md) for the full flow.
This reference is for using individual interfaces or understanding their contracts.
The site follows `master`; pages marked **0.4 development** require the
[development installation](../development/0.4.md), not published 0.3.0.
The [stable release notes](../releases/0.3.0.md) describe the released scope.

## Commands and parameters

### Modern compiler workflows

Each linked command guide describes its options, outputs and refusals. Modern
`inspect`, `generate` and `execute` are part of the compiler workflows, not the
historical pipeline.

| What you need | Where to look |
| --- | --- |
| Acquire a Git snapshot | [HTTPS](git-sources.md) / [SSH](git-ssh.md) |
| Build and publish service images | [OCI plugin](oci-service-plugin.md) |
| Sign and transport delivery proofs | [Attest](attest-delivery-plugin.md) / [OCI proofs](attest-oci-artifacts.md) |
| Invoke an already installed extension | [Extension invocation](extension-invocation.md) |
| Install and list local extensions offline | [Local extensions](local-extensions.md) |
| Configure readiness and exposure with a project file | [Project configuration](../getting-started/user-guide/project.md) |
| Call repository readiness, planning and generation from Python | [Compiler API](compiler-api.md) |
| Plan and build REST/MCP from a repository | [Repository exposure](../getting-started/user-guide/exposure.md) |
| Inventory a Python repository | [Scanner](../getting-started/user-guide/scan.md), [graph](../getting-started/user-guide/graph.md) and [repository readiness](../getting-started/user-guide/repository-readiness.md) |
| Generate MCP from a Python file or notebook | [MCP guide](../getting-started/user-guide/mcp.md) |
| Execute under a policy | [Local and OCI execution](../getting-started/user-guide/execute.md) |
| Inspect one Python file or notebook without execution | [Inspection guide](../getting-started/user-guide/inspect.md) and [readiness policy](../architecture/capability-readiness-v1.md) |
| Generate REST from a Python file or notebook | [REST guide](../getting-started/user-guide/rest.md) and [generator contract](../architecture/rest-generator-v1.md) |
| Inspect source using the independent typed Python API | [Capability IR v1](../architecture/capability-ir-v1.md), including serialization, digests and diagnostics |
| Understand guarantees and limits | [Artifact principles](../architecture/artifact-principles.md), [security baseline](../architecture/security-baseline.md) |

The [MCP generator contract](../architecture/mcp-generator-v1.md) describes the
Tools backend and the interface semantics shared with REST.

### Legacy pipeline — compatibility

These entries describe the historical pipeline and its HTTP generation service,
separately from the modern compiler commands above.

| What you need | Where to look |
| --- | --- |
| Run one pipeline stage from the command line | [Python analysis](../getting-started/user-guide/code-analyzr.md), [FastAPI generation](../getting-started/user-guide/fast-apizr.md), [Docker generation](../getting-started/user-guide/dockerizr.md) |
| Understand or call a pipeline component | [Notebook conversion](../modules/notebook-transformr.md), [Python analysis](../modules/code-analyzr.md), [FastAPI generation](../modules/fast-apizr.md), [Docker generation](../modules/dockerizr.md) |
| Generate files through Apizr's HTTP service | [Service setup and project upload](../apis/apizr-api.md), with the stage endpoints in the same navigation group |
| Understand compatibility guarantees | [Legacy behavior contract](../architecture/legacy-behavior-contract.md) |

The HTTP generation service is Apizr's own interface for producing files. It is
separate from the business API produced by a conversion; the generated
application exposes its own `/docs` schema when started.

The historical pipeline and Capability IR remain independent. The new REST
generator consumes IR and readiness; legacy FastApizr and Dockerizr retain their
existing analysis and output.

## Policies and formats

Use the existing JSON contracts; these links explain their fields and validation.
Project TOML configuration in 0.4 references policy files rather than replacing
the policy languages.

| Format or parameter group | Specification |
| --- | --- |
| Scan exclusions and source roots | [Scanner parameters](../getting-started/user-guide/scan.md) |
| Readiness policy and reports | [Repository readiness](../architecture/repository-readiness-v1.md) |
| Exposure policy and plan | [Exposure Plan v1](../architecture/exposure-plan-v1.md) |
| Bundle artifacts and manifests | [Repository Bundle v1](../architecture/repository-bundle-v1.md) |
| Direct/governed execution choices | [Exposure guide](../getting-started/user-guide/exposure.md) |
| Worker execution policy | [Execution Policy v1](../architecture/execution-policy-v1.md), [OCI v2](../architecture/oci-container-runtime-v1.md) |
| Project and explicit user configuration (0.4) | [Project configuration](../getting-started/user-guide/project.md), [plugin declarations and locks](project-plugin-locks.md) |
| Extension invocation messages (0.4) | [Extension protocol](extension-invocation.md) |

## Python APIs

The [compiler API](compiler-api.md) is available in **development 0.4**, independently
of the CLI. Existing lower-level contracts are documented alongside the
[Capability IR](../architecture/capability-ir-v1.md),
[readiness](../architecture/capability-readiness-v1.md) and generator architecture.
