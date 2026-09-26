# Supported-runtime security baseline

Recorded 2026-09-20, against foundation commit
`d07222800f63f5bc17516878583e69810dc7330e`. This record concerns the historical
notebook/script → AST metadata → FastAPI → container pipeline.

## Runtime policy and migration

Apizr and generated applications now target **Python 3.11–3.14**. Distribution
metadata requires `>=3.11,<3.15`; Ruff and Pyright target 3.11. Compatibility
and container CI cover all four versions; installed-wheel checks cover both
endpoints. Python 3.8–3.10 are deliberately dropped to remove obsolete
compatibility machinery and dependency variants with unresolved advisories.
Python 3.8 and 3.9 are end-of-life; 3.10 approaches its October 2026 end of
security support ([Python lifecycle](https://devguide.python.org/versions/)).

Upgrade the interpreter and replace explicit 3.8–3.10 targets in CLI arguments
and YAML with a supported target. The generation interpreter must still be at
least as recent as its target. Unsupported targets, including 3.15, produce
an explicit supported-range error. This is a deliberate compatibility break.
The package remains **0.2.0**, whose release notes are still marked unreleased;
version selection remains part of the documented publication procedure.

`apizr.compat` is removed. Its active branches on supported interpreters are
replaced directly: `ast.unparse`, `importlib.metadata`,
`sys.stdlib_module_names`, `Path.is_relative_to`, and `typing.get_type_hints`.
Resolved-path containment is retained before writing/copying. Annotation,
stdlib inference, API runtime typing, and traversal regressions exercise these
replacements. The AST branches for pre-3.9 subscript nodes are removed.
`apizr.runtime` now holds target policy and validation, not backports.
Direct dependencies on `astunparse`, `stdlib-list`, `importlib-metadata`, and
`typing-extensions` are removed. Transitive typing-extensions remains owned by
its consumers. Analyzer discovery and pipeline execution semantics are unchanged.

## Dependency decisions

The universal lock was regenerated for the new interpreter range. Updating
only the lock would leave vulnerable fresh installations permitted by overly
broad lower bounds, so the following direct requirements were also reviewed.
Advisory IDs below are from the recorded pip-audit database; aliases can refer
to the same underlying defect. A finding does not establish exploitability in
Apizr's particular use of that dependency.

| Requirement | Previous floor | New floor | Reason |
| --- | --- | --- | --- |
| nbconvert | 7.16 | 7.17.1 | PYSEC-2026-1691: Windows Inkscape lookup; 2229: writes outside intended directory; 2230: file exposure through image embedding. 7.17.1 covers all recorded fixes. |
| Black | 24.8 | 26.3.1 | PYSEC-2026-2120 concerns its GitHub Action; 2121 concerns cache filename/options handling. 26.3.1 covers both; Black remains a notebook-formatting runtime dependency. |
| python-multipart | 0.0.18 | 0.0.31 | PYSEC-2026-1852 and 3036–3040 cover optional upload path handling, query parsing and multipart resource limits. 0.0.31 is the highest required fix. |
| pytest | 8.3 | 9.0.3 | PYSEC-2026-1845: unsafe temporary-directory handling on Unix in earlier versions. |
| FastAPI | 0.115 | 0.141 | Establish a current tested API dependency family, retaining `<1`. Both the lower-bound and locked releases run the generated-API tests. |
| Starlette | indirect | 1.3.1 | Necessary security floor: fixes the recorded parser/path/host/static-file advisory set, including PYSEC-2026-248 and 249. No exact pin or independent upper bound. |
| Pydantic | 2.10 | 2.12 | Functional compatibility: 2.10.0 failed the existing default-body generated-route test with FastAPI 0.141.0. 2.12.0 passes and introduces official Python 3.14 support. This is not a vulnerability claim. |
| IPython | 7.34 | 9 | Remove the obsolete compatibility family from notebook transformation; tested with the other runtime minima. |
| pytest-cov | 5 | 7 | Use the current coverage integration on all supported interpreters; keep the existing 55% branch-aware floor. |
| pre-commit | 3.5 | 4 | Use the current supported tool family after dropping old interpreters. |

FastAPI **0.141.0 and 0.141.1 still declare `starlette>=0.46.0`** in
[published metadata](https://pypi.org/pypi/fastapi/0.141.1/json). The reviewed
0.135–0.140 releases do too. Therefore raising FastAPI alone cannot guarantee
the currently required Starlette fixes. The direct `starlette>=1.3.1` floor is
technically necessary until FastAPI raises its own minimum. It is also emitted
in generated server requirements. FastAPI retains ownership of its compatible
upper range. Pydantic's minimum is likewise shared with generated applications
([2.12 release](https://pydantic.dev/articles/pydantic-v2-12-release)).

The existing Jinja2 floor 3.1.6 already includes its required fixes. Uvicorn,
PyYAML, questionary and packaging retain their existing bounds after functional
minimum-version testing and review of the resolved graph. HTTPX, Ruff, Pyright,
MkDocs, Material, plantuml-markdown, pip-audit and the Hatchling build backend
retain their bounds: no new advisory-driven direct minimum was identified in
this audit. Ruff remains the only repository formatter. Documentation and
security tooling are audited, rather than exempted. Build-backend installation
is separately exercised by wheel/sdist builds; isolated build dependencies are
not represented as project dependency groups in uv.lock.

Transitive dependencies remain resolver-owned; they are not all promoted to
direct requirements. The lock and its blocking audit are the tested supply-chain
baseline. The following previously affected variants are no longer selected:

| Package | Previous affected versions | Current lock |
| --- | --- | --- |
| anyio | 4.5.2, 4.12.1 | 4.15.1 |
| black | 24.8.0, 25.11.0 | 26.5.1 |
| bleach | 6.1.0, 6.2.0 | 6.4.0 |
| click | 8.1.8 | 8.5.0 |
| filelock | 3.16.1, 3.19.1 | 3.32.7 |
| markdown | 3.7 | 3.10.3 |
| nbconvert | 7.16.6 | 7.17.1 |
| pygments | 2.19.2 | 2.21.0 |
| pymdown-extensions | 10.15, 10.21.3 | 12.0.1 |
| pytest | 8.3.5, 8.4.2 | 9.1.1 |
| python-dotenv | 1.0.1, 1.2.1 | 1.2.3 |
| python-multipart | 0.0.20 | 0.0.32 |
| requests | 2.32.4, 2.32.5 | 2.34.2 |
| soupsieve | 2.7, 2.8.4 | 2.9.2 |
| starlette | 0.44.0, 0.49.3 | 1.6.0 |
| tornado | 6.4.2 | 6.5.10 |
| urllib3 | 2.2.3, 2.6.3 | 2.8.0 |
| wheel | 0.45.1 | Removed with the astunparse dependency chain |

Requests/urllib3 fixes are obtained through updated tooling resolution, with
no hand-maintained requirements file or additional transitive pin.

## Audit evidence and scope

The new audit exports PEP 751 lockfiles from the actual `uv.lock`, separately
for each scope, retaining all Python/platform variants. Every scope is blocking,
including audit collection errors. There are no ignored advisories. A regression
test verifies that the union of these exports equals every external package and
version in the universal lock. Shared dependencies can occur in several scopes;
counts must not be summed as unique packages.

| Scope | Resolved entries | Distinct findings | Exit |
| --- | --- | --- | --- |
| Runtime | 72 | 0 | 0 |
| Development/test | 28 | 0 | 0 |
| Documentation | 30 | 0 | 0 |
| Security tooling | 29 | 0 | 0 |

The union contains **125 external package/version pairs**, down from 243.
The editable project is not a third-party dependency. No unresolved dependency
finding remains in this dated audit. This does not promise that future advisory
databases or new unconstrained resolutions will remain clear.

## Verification and retained boundaries

The starting Python 3.11 suite passed **55 tests**, with **56.13%** combined
statement/branch coverage. The updated suite passes **71 tests** on Python
3.11–3.14. Coverage is **56.39% on 3.11–3.13** and **56.07% on 3.14**;
the 55% floor is unchanged. Lower coverage areas remain interactive prompts,
standalone module entry points and parts of the legacy AST model. Added tests
cover unsupported targets, output containment and completeness of scoped audits.
No historical fixture corpus or meaningful behavior test is removed.

The existing deterministic script and notebook tests compare generated artifact
contents across different output directories in an identical environment, deny
network connections and prove source is not executed during generation. They
separately demonstrate that importing the generated application executes the
source module. Generated applications require trusted code; generation is not
a sandbox or a safety certification. Upload traversal (including Windows paths),
size limits, malformed input and non-empty output-directory protections remain
covered. Container smoke tests check non-root execution and actual API requests.

The CodeQL workflows remain enabled. A local test result is not a CodeQL result;
only the completed GitHub analysis for the PR's commit establishes that gate.
See the PR checks for hosted matrix, container and CodeQL execution evidence.

## Reproduction

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv build
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.11
uv run python scripts/smoke_wheel.py dist/*.whl --python 3.14
uv run python scripts/smoke_container.py --python-version 3.11
uv run python scripts/smoke_container.py --python-version 3.14
uv run --group security python scripts/audit_dependencies.py --output /tmp/apizr-audit.json
```

For an additional lower-bound functional check, create a separate Python 3.11
virtual environment and install the editable project with
`uv pip install --resolution lowest-direct --editable . 'pytest>=9.0.3,<10' 'pytest-cov>=7,<8' 'httpx>=0.28,<1'`
using that environment's `--python` path. Run its `python -m pytest --cov`.
This exercises direct minima with resolved transitives; it is not an exhaustive
test of every allowed dependency combination.
