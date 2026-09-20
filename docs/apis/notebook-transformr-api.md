# Notebook Transformr API

`POST /notebook/convert_notebook` on the main service accepts a multipart notebook `file` and returns `{"script": "..."}`. Magics and shell commands are rejected; cells are never executed during conversion.

Alternatively run `uv run uvicorn src.modules.notebook_transformr.app:app`; the standalone route is `/convert_notebook`.

Use `/process_file/` for a complete downloadable project. Callers cannot choose server-side output paths.
