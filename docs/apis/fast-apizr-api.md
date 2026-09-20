# Fast Apizr API

`POST /fastapi/get_fastapi_code/` on the main service accepts a JSON body containing `conf` (FastApizrConfiguration) and `analyse` (AST metadata). It returns the generated Python code as plain text.

Alternatively run `uv run uvicorn apizr.modules.fast_apizr.app:app`; the standalone route is `/get_fastapi_code/`. The automatically generated `/docs` describes the request schema.
