# Using Dockerizr

Generate dependency and Docker files for an existing FastAPI project:

```sh
uv run python -m src.modules.dockerizr.main --project_path .output/api --module_name business_api --force
```

Use `--action requirements` or `--action dockerfile` to run an individual generator. YAML configuration accepts `DockerizrConfiguration` fields directly (without the top-level `dockerizr` key used by the complete pipeline).

The generated startup script runs Uvicorn. The optional `--action gunicorn` produces legacy Gunicorn configuration instead; install `gunicorn` and `uvicorn-worker` in the target environment if using it.

Prefer the main `apizr` CLI for a complete notebook or script conversion; it keeps the module names and paths consistent automatically.
