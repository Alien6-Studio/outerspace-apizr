# Development setup

Use Python 3.8–3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
git clone https://github.com/Alien6-Studio/outerspace-apizr.git
cd outerspace-apizr
uv sync --locked
make lint
make test
make build
```

`pyproject.toml` defines the package and dependency groups. `uv.lock` is the only lockfile. Use `uv lock --upgrade` deliberately when updating dependencies and commit the resulting lockfile with the tested changes.

```sh
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
uv run python scripts/smoke_container.py
```

The smoke test requires Docker and exercises the generated application in a real container. It removes its container and image afterward. Ordinary tests use temporary directories and FastAPI's test client.

The supported import path is `src`, retained for compatibility with the original distribution. Run modules with `python -m src.modules.code_analyzr.main`, for example; do not modify `sys.path` or execute nested `main.py` files directly.

Historical AST fixtures remain under `test/`. The maintained executable suite is under `tests/` and is collected by `pytest`.

The CI matrix covers Python 3.8–3.14, including wheel installation outside the checkout. A separate container matrix generates projects using Python 3.14 and builds/runs each target image (3.8–3.14). Run locally with `uv run --python 3.8 --locked pytest` or `uv run python scripts/smoke_container.py --python-version 3.8`. Historical AST fixture directories 3.8, 3.9, 3.10 and 3.11 are selected by the corresponding test interpreter.
