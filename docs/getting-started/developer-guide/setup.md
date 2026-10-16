# Development and checks

<span id="development-setup"></span>

Use Python 3.11–3.15, Git and uv already installed on your workstation.
This page covers work on Apizr itself; the [development installation](../../development/0.4.md#install-a-development-wheel)
shows how to acquire a checkout and test an unreleased wheel separately.
For using Apizr, start with [Install Apizr](../install.md).

`pyproject.toml` defines the package and dependency groups; `uv.lock` locks the
product environment. Use `uv lock --upgrade` deliberately for dependency updates and commit
the resulting lockfile with the tested changes. The installed namespace is
`apizr`, with a conventional `src/apizr/` layout.

See [Code organization](../../architecture/code-organization.md) for CLI adapters,
core plugin management, compiler domains and the supported compatibility imports
on the `0.4.6` development branch.

Documentation, site and example changes use a separate environment under
`tools/docs/`, without installing the checkout package or invoking Attest:

```sh
uv sync --project tools/docs --locked
uv run --project tools/docs --locked pytest -c tools/docs/pyproject.toml tests/test_ci_scope.py tests/test_dco.py tests/test_docs_publication.py tests/test_site_refonte.py tests/ci/test_release_consistency.py
uv run --project tools/docs --locked mkdocs build --strict
uv run --project tools/docs --locked python scripts/check_docs_html.py
```

See [documentation CI and publication](../../contributing/releases.md#web-only-changes)
for the classifier boundary and installed public example checks. Mixed changes
still require the product checks below.

<span id="foundation-quality-gates"></span>

## Quality gates

```sh
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
python3 scripts/check_package_architecture.py
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
uv run coverage report --include='src/apizr/cli/commands/exposure.py' --fail-under=90
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
The legacy metadata and pipeline engine were removed in 0.4.6.

Coverage has a global 90% branch-aware floor and independent 90% domain floors,
including Exposure (see CI for the full
list). Exposure also uses strict Pyright. Generated applications are tested functionally; their temporary
files and subprocess execution are not included in the package coverage metric.

The security audit exports the resolved `uv.lock` graph for runtime, development,
documentation and security-tooling scopes, then runs `pip-audit --locked`. Findings
and collection failures block the check. No advisories are automatically ignored.
See [SECURITY.md](https://github.com/Alien6-Studio/outerspace-apizr/blob/v0.4.6/SECURITY.md)
for private reporting and execution boundaries.

## Compatibility and packaging

CI tests Python 3.11–3.15. One package job builds wheel/sdist and checks wheel
installation outside the checkout on Linux Python 3.11–3.15 and macOS
3.11, 3.14 and 3.15. A separate container
matrix generates projects with Python 3.14 and builds/runs target images for all
five supported versions.

```sh
uv run --python 3.11 --locked pytest
uv run python scripts/smoke_container.py --python-version 3.11
```

The container smoke test requires Docker, exercises the generated application,
and removes its container/image afterward. Ordinary tests use temporary
directories and FastAPI's test client.

<span id="adversarial-characterization"></span>

## Characterization and fixtures

The [historical pipeline note](../../architecture/legacy-behavior-contract.md)
records its removal. Shared compiler JSON fixtures remain under
`tests/fixtures/characterization/`. Immutable notebook input/export/script goldens
live in `tests/fixtures/notebooks/exporter/`; modern source admission, non-execution
and mutation controls remain active. Do not regenerate goldens simply to make a
changed implementation pass.

Documentation tooling has its own environment, without installing Apizr or its
plugins and without invoking Attest:

```sh
uv sync --project tools/docs --locked
uv run --project tools/docs --locked pytest -c tools/docs/pyproject.toml tests/test_ci_scope.py tests/test_dco.py tests/test_docs_publication.py tests/test_site_refonte.py tests/ci/test_release_consistency.py
uv run --project tools/docs --locked mkdocs build --strict
uv run --project tools/docs --locked python -m scripts.qualification.docs.check_docs_html
```

## Work on the documentation

```sh
uv run --group docs mkdocs serve
uv run --group docs mkdocs build --strict
```

Keep user workflows in **Guides**, interface details and current contracts in
**Reference**, and maintainer tasks in **Contributing**. Keep documentation focused
on supported behavior, reproducible checks and current policy; do not commit
work-session journals or workstation inventories.
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

Linux CI runs the complete ordinary suite on Python 3.11–3.15, plus the separate
Docker/OCI boundary suite. macOS CI runs the ordinary suite
on Python 3.11, 3.14 and 3.15. OCI isolation is qualified against a Linux Docker host,
not a macOS container engine. Windows is outside the validated support matrix;
local-process supervision and safe output creation depend on POSIX facilities.

CI retains JUnit, branch-coverage and mutation reports. See
[build verification](../../contributing/verification.md) and
[dependency maintenance](../../contributing/dependencies.md).

## Optional installation paths (0.3)

The base wheel depends only on Pydantic. Select `notebook`, `http`, `mcp`,
`clients` or `preparation` explicitly; extras can be combined. The `legacy` extra
is removed. `uv sync --locked` installs
the development group, which includes all optional dependencies for validation.

The package job tests the base wheel and each extra in separate environments on
Python 3.11 and 3.14. Security audits cover the base, each extra, and validation
groups; archived SBOMs distinguish the base and combined optional runtime.

The coordinated 0.4.6 packages are prepared on the official `0.4.6` development
branch. Contributor changes target that branch until the maintainer validates
it and merges through the protected stable branch. Publication follows that
separate approval. See
[release governance](../../contributing/release-branches.md) for the active rules.
All four packages declare 0.4.6. Integration and contributor builds do not replace
immutable published archives.
