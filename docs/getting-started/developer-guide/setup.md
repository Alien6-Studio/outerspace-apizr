# Development and checks

<span id="development-setup"></span>

Follow [Start here](../introduction.md#install-the-development-checkout) to install
Python 3.11–3.14, uv and a checkout. This page covers work on Apizr itself.

`pyproject.toml` defines the package and dependency groups; `uv.lock` is the only
lockfile. Use `uv lock --upgrade` deliberately for dependency updates and commit
the resulting lockfile with the tested changes. The installed namespace is
`apizr`, with a conventional `src/apizr/` layout.

<span id="foundation-quality-gates"></span>

## Quality gates

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv run coverage report --include='src/apizr/capabilities/*' --fail-under=90
uv run pre-commit run --all-files
uv build
uv run python scripts/smoke_wheel.py dist/*.whl
uv run --group docs mkdocs build --strict
uv run --group security python scripts/audit_dependencies.py
```

Ruff is the repository linter and formatter. Black remains a runtime dependency
of notebook conversion. Pyright uses standard mode on production/tooling code and
strict mode for `apizr.capabilities`, targeting Python 3.11 syntax and APIs.
Dynamic legacy metadata and pipeline state still have incomplete inferred types.

Coverage has a global 55% branch-aware floor and a separate 90% floor for the
capability core. Generated applications are tested functionally; their temporary
files and subprocess execution are not included in the package coverage metric.
Point-in-time coverage measurements belong in the [engineering archive](../../architecture/records.md).

The security audit exports the resolved `uv.lock` graph for runtime, development,
documentation and security-tooling scopes, then runs `pip-audit --locked`. Findings
and collection failures block the check. No advisories are automatically ignored.
See [SECURITY.md](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/SECURITY.md)
for private reporting and execution boundaries.

## Compatibility and packaging

CI tests Python 3.11–3.14. One package job builds wheel/sdist and checks wheel
installation outside the checkout on Python 3.11 and 3.14. A separate container
matrix generates projects with Python 3.14 and builds/runs target images for all
four supported versions.

```sh
uv run --python 3.11 --locked pytest
uv run python scripts/smoke_container.py --python-version 3.11
```

The container smoke test requires Docker, exercises the generated application,
and removes its container/image afterward. Ordinary tests use temporary
directories and FastAPI's test client.

<span id="adversarial-characterization"></span>

## Characterization and fixtures

The [legacy behavior contract](../../architecture/legacy-behavior-contract.md)
records intentional support, explicit rejections, observed behavior and future
candidates. Its corpus lives in `tests/fixtures/characterization/`, with tests in
`tests/characterization/`. Capability IR uses separate expectations under
`tests/capabilities/`.

```sh
uv run pytest tests/characterization tests/capabilities
```

Hypothesis retains its failure database in `.hypothesis/` and prints replay
information. Preserve failing examples when reporting defects. Generated-application
imports in tests execute trusted fixtures only.

Historical fixtures remain unchanged under `tests/fixtures/legacy/`; the Python
3.11 golden set runs on all supported interpreters. Do not update historical
expectations merely to make a changed implementation pass.

## Work on the documentation

```sh
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
```

Keep user workflows in **Guides**, interface details and current contracts in
**Reference**, and maintainer tasks in **Contributing**. Place dated audits and
verification reports in the **Engineering archive**, with links to current policy.
Preserve published page URLs where possible. Reuse a canonical explanation with
cross-links rather than copying it into several audience sections.

The [publication workflow](../../contributing/releases.md#documentation-publication)
deploys the documentation automatically after a merge to `master`.
