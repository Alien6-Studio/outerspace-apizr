# Development and checks

<span id="development-setup"></span>

Follow [Start here](../introduction.md#install) to install
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
uv run coverage report --include='src/apizr/readiness/*' --fail-under=90
uv run coverage report --include='src/apizr/generators/rest/*' --fail-under=90
uv run coverage report --include='src/apizr/generators/mcp/*' --fail-under=90
uv run coverage report --include='src/apizr/interfaces/*' --fail-under=90
uv run coverage report --include='src/apizr/execution/*' --fail-under=90
uv run coverage report --include='src/apizr/governed/*' --fail-under=90
uv run coverage report --include='src/apizr/repository/*' --fail-under=90
uv run coverage report --include='src/apizr/graph/*' --fail-under=90
uv run coverage report --include='src/apizr/exposure/*' --fail-under=90
uv run coverage report --include='src/apizr/exposure_cli.py' --fail-under=90
uv run coverage report --include='src/apizr/execution/worker.py,src/apizr/execution/supervisor.py,src/apizr/execution/protocol.py' --fail-under=90
uv run pre-commit run --all-files
uv build
uv run python scripts/smoke_wheel.py dist/*.whl
uv run --group docs mkdocs build --strict
uv run --group security python scripts/audit_dependencies.py
```

Ruff is the repository linter and formatter. Black remains a runtime dependency
of notebook conversion. Pyright uses standard mode on production/tooling code and
strict mode for `apizr.capabilities`, `apizr.readiness` and `apizr.generators.rest`, targeting Python 3.11 syntax and APIs.
Dynamic legacy metadata and pipeline state still have incomplete inferred types.

Coverage has a global 90% branch-aware floor, a separate 59.5% measured legacy
floor, and 90% floors for modern packages including Exposure (see CI for the full
list). Exposure also uses strict Pyright. Generated applications are tested functionally; their temporary
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
`tests/capabilities/`; static readiness and inspection tests live in `tests/readiness/`.

```sh
uv run pytest tests/characterization tests/capabilities tests/readiness tests/rest tests/mcp_generator
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

The independent OCI isolation suite needs an explicitly built local worker image:

```sh
uv build
uv run python scripts/build_worker_image.py dist/*.whl --output /tmp/apizr-worker-image.json
APIZR_TEST_OCI_IMAGE=/tmp/apizr-worker-image.json uv run pytest tests/oci tests/governed_oci \
  --cov=apizr.oci --cov=apizr.governed_oci --cov-report=term-missing --cov-fail-under=90
uv run coverage report --include='src/apizr/oci/*' --fail-under=90
uv run coverage report --include='src/apizr/governed_oci/*' --fail-under=90
uv run python scripts/smoke_wheel.py dist/*.whl \
  --runtime-image-config /tmp/apizr-worker-image.json
```

The Linux `oci-isolation` CI job requires real Docker controls and checks for leaked
invocation containers. Normal compatibility jobs run OCI model/planner/unit tests
without Docker; integration tests skip only when no explicit image was supplied.
Image building is a deliberate preparation step and may access registries. Test
invocations never pull. Remove the locally built image by its printed ID when no
longer needed. See the [backend contract](../../architecture/oci-container-runtime-v1.md).

Repository scanner/catalog tests live in `tests/repository/` and require no Docker.
The new package and scan CLI use strict Pyright; each compatibility job enforces
a separate 90% branch-aware repository coverage floor. Catalog and schema goldens
are under `tests/fixtures/catalog/` and `docs/specs/`. See the
[scanner contract](../../architecture/repository-scanner-v1.md) before changing discovery policy.


## Operating-system validation

Linux CI runs the complete ordinary suite on Python 3.11–3.14, plus the separate
Docker/OCI boundary suite and legacy containers. macOS CI runs the ordinary suite
on Python 3.11 and 3.14. OCI isolation is qualified against a Linux Docker host,
not a macOS container engine. Windows is outside the validated support matrix;
local-process supervision and safe output creation depend on POSIX facilities.

CI retains JUnit, branch-coverage and mutation reports. See
[build verification](../../contributing/verification.md) and
[dependency maintenance](../../contributing/dependencies.md).

## Optional installation paths (0.3 development)

The base wheel depends only on Pydantic. Select `notebook`, `http`, `mcp`, or
`legacy` extras for their respective workflows; extras can be combined.
For example, `python -m pip install ".[legacy]"` retains the full historical
0.2.1 pipeline dependency stack from this checkout. `uv sync --locked` installs
the development group, which includes all optional dependencies for validation.

The package job tests the base wheel and each extra in separate environments on
Python 3.11 and 3.14. Security audits cover the base, each extra, and validation
groups; archived SBOMs distinguish the base and combined optional runtime.
