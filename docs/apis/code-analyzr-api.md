# Code Analyzr API

On the main service, `POST /code/analyze_file/` accepts a multipart Python `file`. Optional query parameters `functions_to_analyze` and `ignore` select functions by comma-separated names. The response is JSON metadata.

Alternatively run `uv run uvicorn apizr.modules.code_analyzr.app:app`; the standalone route is `/analyze_file/`.

The former directory-scanning endpoint is removed. Upload the file to analyze instead of granting callers access to server paths.

In 0.3, class declarations appear in an optional `classes` array, separate from
exposed functions. See the [inventory fields and boundaries](../modules/code-analyzr.md#classes-and-methods-in-03).
Ambiguous selected function definitions (including overload sets) return HTTP 400
before any generated application is imported.
