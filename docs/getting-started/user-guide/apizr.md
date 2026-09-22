# Using Apizr

With Apizr installed, download the [example pricing notebook](https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/master/examples/pricing.ipynb)
to `examples/pricing.ipynb`, then:

```sh
uv run apizr --notebook examples/pricing.ipynb --output-dir .output/pricing --force
uv run uvicorn pricing_api:app --app-dir .output/pricing --host 127.0.0.1 --port 5001
```

POST `{"prices": [10, 20]}` to `/total` to obtain `36.0`. Visit `/docs` for the generated API schema.

```sh
apizr --notebook examples/pricing.ipynb --output-dir .output/pricing-image --build-image apizr-pricing:local
docker run --rm -p 127.0.0.1:5001:5001 apizr-pricing:local
```

`--build-image TAG` generates the project and builds a local Docker image in one
command. Success JSON
includes the image tag and immutable image ID. Build logs go to stderr; a failed
build returns a nonzero exit status and retains the generated project for diagnosis.
Docker must be installed and running. This explicit action can fetch base images
and install dependencies; it does not run a notebook kernel, start a service or
push the image. Without this option, generation still works without Docker.

Use `--script file.py` for Python source. The filename must be a valid Python module name. Output defaults to `.output/<source>` and must be empty. A YAML file can be supplied with `--configuration`; `src/apizr/configuration.yaml` is the reference example. `fast_apizr.api_filename` controls the generated filename.

Use `--requirements requirements.txt` to provide application dependencies explicitly. Otherwise imports are analyzed without execution, with installed distributions pinned when identifiable. Dynamic imports and ambiguous dependencies need an explicit requirements file.

Use repeated `--include PATH` flags for data/config files or directories, relative
to the notebook/script directory. Their relative paths are preserved in the output
and image. Only selected resources and existing local Python imports are copied;
there is no automatic scan for application data or secrets. Hidden/cache paths,
symlinks, special files, paths outside the source directory and collisions with
generated files are refused. Review the selected files before distributing them.
Keep credentials outside the image and supply them at runtime.

For a notebook next to `settings.json`, `data/`, `requirements.txt` and `config.yaml`:

```sh
apizr --notebook project/model.ipynb --output-dir .output/model \
  --configuration project/config.yaml --requirements project/requirements.txt \
  --include settings.json --include data --build-image model:local
```

The generation configuration controls the Docker base, system packages, server
port/workers and startup script. Application settings/data are included explicitly;
the generation YAML itself is not silently embedded. Files requiring pip options,
nested requirement includes or local dependency paths must first be converted to
self-contained package requirements. Building remains trusted-code oriented:
dependency installation and configured startup hooks can execute code.

Use `--skip-docker` for an API-only project. `--skip-fastapi` also requires `--skip-docker`. `--skip-pipreqs` disables dependency inference; Docker generation still requires an explicit requirements file.

`--build-image` cannot be combined with `--skip-docker`. To extend the legacy
pipeline without patching Apizr, explicitly enable a trusted installed
[pipeline plugin](../developer-guide/plugins.md) with `--plugin NAME`.

Top-level functions become POST routes. Async functions, argument defaults and supported Pydantic annotations are preserved. Magics, shell commands and variadic signatures are rejected. Starting the resulting API imports the original code; run trusted inputs only.

Use `--python-version 3.11` (or YAML `python_version: [3, 11]`) to select a target explicitly. The default is the running interpreter. Apizr must run on Python at least as recent as its target and does not transpile newer code. Dependencies inferred for a different target are left unpinned so the target installer can select compatible releases.
