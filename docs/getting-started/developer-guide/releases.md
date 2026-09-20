# Migration and releases

## 0.2.0 — unreleased

- **Python 3.11–3.14 only**, for both Apizr and generated targets. Python 3.8, 3.9 and 3.10 are deliberately dropped for security and maintenance reasons. The earlier foundation commit supported 3.8–3.14; this revision supersedes that policy.
- Python 3.8/3.9 are end-of-life; 3.10 approaches the end of security support. See the [upstream lifecycle](https://devguide.python.org/versions/). Older runtimes forced vulnerable dependency variants into the universal lock.
- Upgrade your interpreter and deployment image to 3.11 or newer before syncing/installing. Update `--python-version` and YAML `python_version` targets; unsupported targets fail with the supported range. Existing source is parsed, never transpiled.
- The release remains **0.2.0, unreleased**: no version bump or publication is performed by this security PR. The release procedure selects the final available version before publishing.
- Removed `apizr.compat` and obsolete backports. Application APIs remain under `apizr`; consumers of internal compatibility helpers should use the Python standard library.
- Security minima for FastAPI, Starlette, python-multipart, nbconvert, Black and pytest are documented in the [current security baseline](../../architecture/security-baseline.md). Pydantic 2 remains in use.
- One PEP 621 package definition and `uv.lock`; Poetry/PDM lockfiles and separate module requirement files are retired.
- Imports work from an installed wheel, without changing `sys.path`.
- Non-interactive CLI defaults; `--force` remains accepted and `--interactive` enables prompts.
- The pipeline passes the converted script and generated API module through every stage.
- Function defaults, async functions, positional-only and keyword-only arguments are preserved. Dynamic argument lists are explicitly rejected.
- Type resolution uses the original module at API startup, including user-defined Pydantic models.
- Containers use Uvicorn directly, Debian slim by default, a non-root user and a health endpoint.
- Dependency inference no longer runs pipreqs or imports the analyzed modules. Explicit requirements are supported.
- HTTP generation returns a ZIP instead of writing to caller-selected paths. Directory scanning and the old `/dockerize_file/` endpoint are removed. The notebook endpoint returns script text. Docker endpoints return generated content.
- Non-empty output directories are rejected. Choose a new directory when regenerating.

## PyPI ownership

Deleting a PyPI organization does not necessarily delete the package or remove individually assigned project permissions. Verify the `outerspace-apizr` project and its individual **Owner** permissions in the PyPI account before attempting a release. Do not rename or recreate the package merely because an organization was deleted.

A personal PyPI account can maintain the project. Organization accounts are optional; community organizations are free subject to PyPI approval, while corporate accounts are paid. An open-source license alone does not determine the organization's classification.

References: [PyPI organization FAQ](https://docs.pypi.org/organization-accounts/org-acc-faq/), [organization accounts](https://docs.pypi.org/organization-accounts/).

## Release procedure

1. Confirm project ownership, available version number and the target index (TestPyPI or PyPI).
2. Run `make all`, build the docs, and run `uv run python scripts/smoke_container.py`.
3. Verify the wheel in a separate environment outside the checkout and review the release notes.
4. Configure a [Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) for the actual GitHub repository if automated publication is desired. No organization subscription is required.
5. Publish the reviewed artifacts only as a deliberate release action. This repository currently builds artifacts in CI and does not automatically publish to PyPI.

The 0.2.0 changes are not available through `pip install outerspace-apizr` until a release is actually published. Install from this checkout in the meantime.
