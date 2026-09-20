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
