# Code Analyzr

The analyzer uses Python's AST without importing the source module. It extracts top-level functions, imports, argument kinds and default-presence metadata. It supports synchronous and asynchronous functions. Classes and nested functions are not exposed as endpoints.

```python
from apizr.modules.code_analyzr.analyzr import AstAnalyzr
from apizr.modules.code_analyzr.configuration import CodeAnalyzrConfiguration

metadata = AstAnalyzr(
    CodeAnalyzrConfiguration(), "def add(a: int, b: int = 1): return a + b"
).get_analyse()
```

Set `functions_to_analyze` or `ignore` to comma-separated function names. Variadic signatures are rejected rather than silently losing arguments. Runtime types and actual default values are resolved from the original module by the generated API at startup.

## Classes and methods in 0.3

When classes are present, the analysis includes a separate `classes` inventory.
Each declaration records its name, qualified name, source line, base expressions,
class keywords, decorators, directly declared methods and nested classes. Method
records retain the full parameter declaration (including `self`/`cls`, variadics,
annotations and defaults), return annotation, decorators and async marker.

`kind` describes syntax: `instance`, a single `classmethod`, `staticmethod` or
`property` decorator, or `decorated` for other combinations. Decorator aliases,
shadowed builtins, inheritance and runtime-generated members are not resolved.
Declarations inside method bodies or conditional class-body blocks are outside
this inventory. No class is instantiated, no base imported and no decorator run.
Function selection filters apply to `functions`, not to this structural inventory.

Methods do not enter the exposed `functions` list. To publish a method, provide an
explicit top-level wrapper with a supported signature. Capability IR v1 and the
modern REST/MCP contracts still describe top-level functions only.

## Ambiguous definitions

Selected duplicate function names, including overload sets, are rejected during
analysis. FastApizr also refuses duplicate selected route names in externally
supplied metadata. This prevents discovery, request dispatch and OpenAPI from
describing different implementations. Exclude the ambiguous name or replace it
with one unambiguous wrapper; Apizr does not infer an overload dispatch policy.
