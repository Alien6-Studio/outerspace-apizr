# Technical reference

For a first conversion, follow [Generate an API and container](../getting-started/user-guide/apizr.md).
This reference is for using individual interfaces or understanding their contracts.

| What you need | Where to look |
| --- | --- |
| Inspect one Python file or notebook without execution | [Inspection guide](../getting-started/user-guide/inspect.md) and [readiness policy](../architecture/capability-readiness-v1.md) |
| Run one pipeline stage from the command line | [Python analysis](../getting-started/user-guide/code-analyzr.md), [FastAPI generation](../getting-started/user-guide/fast-apizr.md), [Docker generation](../getting-started/user-guide/dockerizr.md) |
| Understand or call a pipeline component | [Notebook conversion](../modules/notebook-transformr.md), [Python analysis](../modules/code-analyzr.md), [FastAPI generation](../modules/fast-apizr.md), [Docker generation](../modules/dockerizr.md) |
| Generate files through Apizr's HTTP service | [Service setup and project upload](../apis/apizr-api.md), with the stage endpoints in the same navigation group |
| Inspect source using the independent typed Python API | [Capability IR v1](../architecture/capability-ir-v1.md), including serialization, digests and diagnostics |
| Understand guarantees and limits | [Legacy behavior contract](../architecture/legacy-behavior-contract.md), [artifact principles](../architecture/artifact-principles.md), [security baseline](../architecture/security-baseline.md) |

The HTTP generation service is Apizr's own interface for producing files. It is
separate from the business API produced by a conversion; the generated
application exposes its own `/docs` schema when started.

The existing pipeline and Capability IR remain independent. Capability IR does
not generate the current FastAPI or Docker output. Historical measurements and
audit reports are kept in the [engineering archive](../architecture/records.md),
separate from the current contracts.
