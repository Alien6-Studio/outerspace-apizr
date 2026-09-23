# Technical reference

For your first project, follow [Start here](../getting-started/introduction.md).
Read the [Capability Compiler overview](../architecture/overview.md) for the full flow.
This reference is for using individual interfaces or understanding their contracts.

| What you need | Where to look |
| --- | --- |
| Configure readiness and exposure with a project file | [Project configuration](../getting-started/user-guide/project.md) |
| Call repository readiness, planning and generation from Python | [Compiler API](compiler-api.md) |
| Inventory a Python repository | [Scanner](../getting-started/user-guide/scan.md), [graph](../getting-started/user-guide/graph.md) and [repository readiness](../getting-started/user-guide/repository-readiness.md) |
| Expose MCP tools | [MCP guide](../getting-started/user-guide/mcp.md) |
| Execute under a policy | [Local and OCI execution](../getting-started/user-guide/execute.md) |
| Inspect one Python file or notebook without execution | [Inspection guide](../getting-started/user-guide/inspect.md) and [readiness policy](../architecture/capability-readiness-v1.md) |
| Generate REST from IR and readiness | [REST guide](../getting-started/user-guide/rest.md) and [generator contract](../architecture/rest-generator-v1.md) |
| Run one pipeline stage from the command line | [Python analysis](../getting-started/user-guide/code-analyzr.md), [FastAPI generation](../getting-started/user-guide/fast-apizr.md), [Docker generation](../getting-started/user-guide/dockerizr.md) |
| Understand or call a pipeline component | [Notebook conversion](../modules/notebook-transformr.md), [Python analysis](../modules/code-analyzr.md), [FastAPI generation](../modules/fast-apizr.md), [Docker generation](../modules/dockerizr.md) |
| Generate files through Apizr's HTTP service | [Service setup and project upload](../apis/apizr-api.md), with the stage endpoints in the same navigation group |
| Inspect source using the independent typed Python API | [Capability IR v1](../architecture/capability-ir-v1.md), including serialization, digests and diagnostics |
| Understand guarantees and limits | [Legacy behavior contract](../architecture/legacy-behavior-contract.md), [artifact principles](../architecture/artifact-principles.md), [security baseline](../architecture/security-baseline.md) |

The HTTP generation service is Apizr's own interface for producing files. It is
separate from the business API produced by a conversion; the generated
application exposes its own `/docs` schema when started.

The historical pipeline and Capability IR remain independent. The new REST
generator consumes IR and readiness; legacy FastApizr and Dockerizr retain their
existing analysis and output. Historical measurements and
audit reports are kept in the [engineering archive](../architecture/records.md),
separate from the current contracts.

The [MCP generator contract](../architecture/mcp-generator-v1.md) describes the
Tools backend and the interface semantics shared with REST.
