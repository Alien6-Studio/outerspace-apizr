# Code Analyzr API

On the main service, `POST /code/analyze_file/` accepts a multipart Python `file`. Optional query parameters `functions_to_analyze` and `ignore` select functions by comma-separated names. The response is JSON metadata.

Alternatively run `uv run uvicorn apizr.modules.code_analyzr.app:app`; the standalone route is `/analyze_file/`.

The former directory-scanning endpoint is removed. Upload the file to analyze instead of granting callers access to server paths.
