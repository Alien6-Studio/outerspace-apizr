# Development setup

Use Python 3.11–3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

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

The installed package is `apizr`, using the conventional `src/apizr/` layout. The former `src` namespace is no longer shipped. Run modules with `python -m apizr.modules.code_analyzr.main`, for example; do not modify `sys.path` or execute nested `main.py` files directly.

Historical fixtures are preserved byte-for-byte under `tests/fixtures/legacy/`. The maintained suite and fixture corpus now share the `tests/` hierarchy.

The compatibility test matrix covers Python 3.11–3.14. A single package job builds once and installs that wheel outside the checkout on Python 3.11 and 3.14. A separate container matrix generates projects using Python 3.14 and builds/runs each target image (3.11–3.14). Run locally with `uv run --python 3.11 --locked pytest` or `uv run python scripts/smoke_container.py --python-version 3.11`. The Python 3.11 golden fixture set is exercised on all supported runtimes; older golden files remain archived unchanged.


## Foundation quality gates

```sh
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv run pre-commit run --all-files
uv build
uv run python scripts/smoke_wheel.py dist/*.whl
uv run --group security python scripts/audit_dependencies.py
```

Pyright uses standard mode on production and tooling code, targeting Python 3.11
syntax and APIs. Obsolete compatibility backports have been removed. There are no blanket diagnostic
disables. Dynamic AST metadata, decorators and mutable pipeline state still have
incomplete inferred types; standard mode is not a claim of strict typing.

Coverage includes legacy modules, reports missing lines, and uses a conservative
55% branch-aware floor against the recorded 55.90% baseline. Generated temporary
applications are exercised functionally, not included in the package coverage
percentage. Subprocess coverage remains separate from this parent-process metric.

Security tools require Python 3.11 or newer. The audit exports `uv.lock` to temporary `pylock.toml` files for runtime, development, documentation and
security-tooling scopes, then runs `pip-audit --locked` on each. All findings
and collection failures are blocking. A regression test checks that their union
covers every locked registry package/version variant. It does not re-resolve a hand-maintained
requirements file or suppress findings. See [SECURITY.md](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/SECURITY.md)
for reporting and execution boundaries.

The CLI entry point is `apizr.main:main`: `main.py` already owns CLI parsing and
the conversion entry point, so it was moved unchanged in responsibility rather
than split into new orchestration modules. Update `src.*` imports and commands
to `apizr.*`; no namespace shim is included.

Python 3.8–3.10 are intentionally no longer supported; see the [migration notes](releases.md). The 55% coverage floor remains unchanged.
