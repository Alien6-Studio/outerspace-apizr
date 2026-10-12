# Documentation environment

Run these commands from the repository root:

```sh
uv sync --project tools/docs --locked
uv run --project tools/docs --locked pytest -c tools/docs/pyproject.toml tests/test_ci_scope.py tests/test_dco.py tests/test_docs_publication.py tests/test_site_refonte.py tests/ci/test_release_consistency.py
uv run --project tools/docs --locked mkdocs build --strict
uv run --project tools/docs --locked python scripts/check_docs_html.py
```

This virtual project installs site and validation tools into `tools/docs/.venv`.
It does not install Apizr or the optional plugins. Its pytest configuration does
not inherit the product coverage plugin or product test collection. The CI
workflow runs the generic file-integrity hooks separately from product hooks.

Example checks install published wheels into separate temporary environments
and execute documented commands outside the checkout. Documentation-only changes
do not build a candidate wheel or invoke Attest, Docker or release qualification.
Mixed product changes retain candidate example checks and full product CI.

The lockfile reuses versions and distribution hashes from the reviewed root
lockfile. `tests/test_ci_scope.py` enforces that relationship; new versions or
dependencies first require the existing dependency source, license and security
review. No package is published from this project.
