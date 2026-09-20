# OuterSpace Apizr

Turn top-level Python functions in a script or Jupyter notebook into a FastAPI application and a Docker project.

**Development version: 0.2.0. Python 3.8–3.14.** This checkout is the source of truth until a new release is published on PyPI.

## Install from the repository

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone https://github.com/Alien6-Studio/outerspace-apizr.git
cd outerspace-apizr
uv sync --locked
uv run apizr --help
```

For an ordinary pip environment, `python -m pip install .` also works. Development dependencies and their exact versions are recorded in `uv.lock`.

## Notebook → API → container

```sh
uv run apizr --notebook examples/pricing.ipynb --output-dir .output/pricing --force
uv run uvicorn pricing_api:app --app-dir .output/pricing --host 127.0.0.1 --port 5001
```

In another terminal:

```sh
curl -f http://127.0.0.1:5001/health
curl -f http://127.0.0.1:5001/total \
  -H 'Content-Type: application/json' \
  -d '{"prices": [10, 20]}'
# 36.0 (the default tax is 20%)
```

Open <http://127.0.0.1:5001/docs> for the generated OpenAPI documentation. Stop the local server before binding the container to the same port:

```sh
docker build -t apizr-pricing .output/pricing
docker run --rm -p 127.0.0.1:5001:5001 apizr-pricing
```

The output contains the converted script, AST metadata, generated API, `requirements.txt`, `Dockerfile`, `start.sh`, and `.dockerignore`. The container runs Uvicorn as a non-root user. Debian slim is the default; Alpine remains configurable.

Use an empty output directory. Existing non-empty directories are rejected to avoid silently overwriting files or retaining stale modules.

## Python compatibility

Apizr runs on Python **3.8 through 3.14**, including the original 3.8–3.11 range. `uv.lock` resolves compatible dependencies for every version rather than imposing recent dependency versions on older interpreters.

By default, generated containers target the interpreter running Apizr. Select an older target explicitly:

```sh
uv run apizr --notebook examples/pricing.ipynb --python-version 3.8 --output-dir .output/pricing38
```

The YAML equivalent is `python_version: [3, 8]`. Run Apizr with an interpreter at least as recent as the target: it parses the source using that target's grammar but does not transpile newer Python features. Input code and its dependencies must support the selected target. When targeting a different interpreter, inferred dependencies are not pinned to versions from the host environment; the target installer resolves compatible versions. Explicit requirements are preserved.

To run the development suite on a specific interpreter:

```sh
uv run --python 3.8 --locked pytest
uv run --python 3.11 --locked pytest
```

## Scripts and configuration

```sh
uv run apizr --script path/to/business.py --output-dir .output/business
uv run apizr --script path/to/business.py --configuration src/configuration.yaml --output-dir .output/configured
uv run apizr --script path/to/business.py --requirements path/to/requirements.txt --output-dir .output/explicit
```

Without configuration the API filename is `<source>_api.py`. `fast_apizr.api_filename` can override it. The business module is derived from the input filename; Docker always starts the actual generated API module.

The CLI is non-interactive by default; `--force` remains accepted. `--interactive` prompts for common settings. Use `code_analyzr.functions_to_analyze` or `code_analyzr.ignore` in YAML to select functions.

`--skip-docker` generates the API without Docker files. `--skip-fastapi` requires `--skip-docker`. The legacy flag `--skip-pipreqs` skips dependency inference; when Docker is enabled, supply `--requirements` instead.

## Supported code and limits

- Top-level synchronous and asynchronous functions; typed JSON arguments, defaults, positional-only and keyword-only parameters.
- Types supported by Pydantic, including lists, tuples, unions, `Literal`, `Annotated` and Pydantic models. Annotations are resolved in the source module when the generated API starts.
- Local sibling `.py` modules and regular Python packages are copied without importing them. Namespace packages, external data/model files, dynamically loaded modules and modules outside the source directory must be packaged explicitly.
- `*args`, `**kwargs`, notebooks without selected functions, notebook magics and shell commands are rejected with an explicit error.
- Classes and nested functions are not exposed as routes. Notebook cell outputs and notebook execution state are not used.
- Generation never executes the source code. **Starting the generated API imports the source module and executes its top-level statements. Only run trusted inputs.** Move interactive code, training and development side effects behind `if __name__ == "__main__":`.
- Input validation errors return HTTP 422; unexpected function failures return HTTP 500 without exposing exception details. Application `HTTPException` responses are preserved.

Dependency inference scans imports without network access. Installed distributions are pinned when identifiable; unknown import names are inferred with common aliases. This is a convenience, not a universal resolver. Use `--requirements` for reproducible application dependencies, private packages or ambiguous imports. Explicit files accept PEP 508 requirements, not pip options or nested `-r` files. Server dependencies are added automatically.

## Local generation service

```sh
uv run uvicorn src.app:app --host 127.0.0.1 --port 8000
curl -f -F 'file=@examples/pricing.ipynb' http://127.0.0.1:8000/process_file/ -o pricing-api.zip
```

Uploads are limited to 10 MiB and generation uses isolated temporary directories. The service returns a ZIP archive; callers cannot select server filesystem paths. Module APIs are mounted at `/code`, `/fastapi`, `/notebook`, and `/docker`, each with its own `/docs`. This service has no authentication and is intended for local use.

## Development and verification

```sh
uv sync --locked
make lint
make test
make build
uv run --group docs mkdocs build --strict
uv run python scripts/smoke_container.py  # requires a running Docker daemon
```

CI tests Python 3.8, 3.9, 3.10, 3.11, 3.12, 3.13 and 3.14, builds the package, installs its wheel outside the checkout, and runs the notebook → Docker → HTTP smoke test. The container smoke test removes its own container and image afterward.

See [migration and release notes](docs/getting-started/developer-guide/releases.md) for changes from 0.1.x and PyPI publication. Creating a PyPI organization is not required to develop or publish a package.

Licensed under [GPL-3.0-or-later](docs/about/LICENSE.md).
