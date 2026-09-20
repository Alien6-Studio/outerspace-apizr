# Fast Apizr

`FastApiAppGenerator` renders a self-contained FastAPI module from AST metadata. Each selected function becomes a POST route with a Pydantic request model. A `/health` endpoint is added.

The generated module imports the original business module at startup. It resolves annotations with `typing.get_type_hints`, preserving supported Pydantic types, forward references, annotated constraints and user models. Defaults are read from the original function signature. Async functions are awaited.

Invalid input returns HTTP 422. Unexpected function failures are logged and return HTTP 500 with a generic message; explicitly raised FastAPI HTTP exceptions are preserved.

Only start generated applications from trusted source code: importing the business module executes its top-level statements.
