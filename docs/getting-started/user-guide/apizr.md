# Using Apizr

From an installed development checkout:

```sh
uv run apizr --notebook examples/pricing.ipynb --output-dir .output/pricing --force
uv run uvicorn pricing_api:app --app-dir .output/pricing --host 127.0.0.1 --port 5001
```

POST `{"prices": [10, 20]}` to `/total` to obtain `36.0`. Visit `/docs` for the generated API schema.

```sh
docker build -t apizr-pricing .output/pricing
docker run --rm -p 127.0.0.1:5001:5001 apizr-pricing
```

Use `--script file.py` for Python source. The filename must be a valid Python module name. Output defaults to `.output/<source>` and must be empty. A YAML file can be supplied with `--configuration`; `src/apizr/configuration.yaml` is the reference example. `fast_apizr.api_filename` controls the generated filename.

Use `--requirements requirements.txt` to provide application dependencies explicitly. Otherwise imports are analyzed without execution, with installed distributions pinned when identifiable. External data, dynamic imports and ambiguous dependencies require manual packaging.

Use `--skip-docker` for an API-only project. `--skip-fastapi` also requires `--skip-docker`. `--skip-pipreqs` disables dependency inference; Docker generation still requires an explicit requirements file.

Top-level functions become POST routes. Async functions, argument defaults and supported Pydantic annotations are preserved. Magics, shell commands and variadic signatures are rejected. Starting the resulting API imports the original code; run trusted inputs only.

Use `--python-version 3.11` (or YAML `python_version: [3, 11]`) to select a target explicitly. The default is the running interpreter. Apizr must run on Python at least as recent as its target and does not transpile newer code. Dependencies inferred for a different target are left unpinned so the target installer can select compatible releases.
