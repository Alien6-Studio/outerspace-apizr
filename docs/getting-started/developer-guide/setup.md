# Development and checks

To propose a change, follow [Contributing to Apizr](../../about/CONTRIBUTING.md).
It explains how to fork the repository and open a PR against `0.4.6`.
This page adds the checks you may need while working on the code.

## Install the development environment

Use Git, uv and Python 3.11–3.15 on macOS or Linux. From your checkout:

```sh
uv sync --locked --group readme
uv run pre-commit install
```

The Python package lives in `src/apizr/`. See
[code organization](../../architecture/code-organization.md) to find the part you
need to change. Keep `uv.lock` with dependency changes so others can use the same
environment.

## Run the relevant checks

Start with the tests for the behavior you changed:

```sh
uv run pytest tests/path/to/test_file.py
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pre-commit run --all-files
```

Replace the test path with the relevant file. For the complete local suite:

```sh
uv run --locked python -m scripts.qualification.packaging.vscode_source --prepare
uv run pytest --cov --cov-report=term-missing
```

The preparation command fetches the reviewed VS Code extension source needed by
integration tests. It does not change the extension repository.

CI tests supported Python versions on Linux and macOS. It also checks coverage,
package contents, dependency security and execution boundaries. See
[build verification](../../contributing/verification.md) for the complete matrix.
Use [SECURITY.md](https://github.com/Alien6-Studio/outerspace-apizr/blob/0.4.6/SECURITY.md)
to report a vulnerability privately.

## Build and test a wheel

```sh
uv build
uv run python scripts/smoke_wheel.py dist/*.whl
```

The smoke test checks an installed wheel outside the checkout. For dependency
updates, also follow [dependency maintenance](../../contributing/dependencies.md).

## Work on the documentation

Website changes use `gh-pages` and a separate environment. Create a branch from
`upstream/gh-pages` in your fork and follow the
[website README](https://github.com/Alien6-Studio/outerspace-apizr/blob/gh-pages/README.md).
The local preview uses:

```sh
uv sync --locked
uv run --locked mkdocs serve
```

Keep examples in the guides, exact options in Reference, and contributor
procedures in Contributing. Preserve existing page URLs and check links before
opening the PR.

## Optional Docker checks

These checks need Docker. Ordinary unit tests do not.

```sh
uv run python scripts/smoke_container.py --python-version 3.11
```

For changes to OCI isolation, build a worker image and run its integration suite:

```sh
uv build
uv run python scripts/build_worker_image.py dist/*.whl --output /tmp/apizr-worker-image.json
APIZR_TEST_OCI_IMAGE=/tmp/apizr-worker-image.json uv run pytest tests/oci tests/governed_oci
```

Remove the locally built image when finished. The
[OCI backend reference](../../architecture/oci-container-runtime-v1.md) describes
the tested boundaries.

## Test fixtures

Notebook exports and published experiment records include frozen compatibility
fixtures. Preserve their original bytes when changing the implementation.
See [notebook history](../../architecture/legacy-behavior-contract.md) and the
[scanner reference](../../architecture/repository-scanner-v1.md) for the relevant
fixtures and expected behavior.

<span id="adversarial-characterization"></span>
<span id="characterization-and-fixtures"></span>
<span id="compatibility-and-packaging"></span>
<span id="development-setup"></span>
<span id="foundation-quality-gates"></span>
<span id="operating-system-validation"></span>
<span id="optional-installation-paths-03"></span>
<span id="quality-gates"></span>
