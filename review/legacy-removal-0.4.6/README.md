# Complete historical pipeline removal — 0.4.6 development

Closes the implementation scope of #284 and #331. The branch is `0.4.6`;
there is no tag, publication, stable-branch change or release authorization here.
Candidate metadata remains 0.4.5 until coordinated promotion.

## Deprecation and exact removed surfaces

`b4fb8b1e` first deprecated the shared FastAPI rendering boundary with both
`DeprecationWarning` and a stderr migration notice. Complete CLI conversions,
standalone FastAPI commands, Python renderer calls and HTTP generation converge
there. Its 263 pipeline/HTTP/plugin/characterization tests passed before removal.
The final tree removes these retired implementations and their dedicated tests.

The [migration table](../../docs/releases/migrate-0.4.6.md#removed-generation-pipeline)
records each CLI, Python, HTTP, YAML and extension entrypoint and its replacement.
The removed trees are `apizr.modules` (CodeAnalyzr, FastApizr and Dockerizr),
`apizr.legacy`, and `apizr.extensions`, including i18n and templates. The six
legacy app/configuration/http/delivery/main/prompt facades are removed with their
owners. The other 73 compatibility facades and embedded aliases remain for #291.

The old complex-notebook YAML and pipeline-plugin examples are retired. Current
ordinary notebooks, SDK/Jupyter examples, installed trusted extensions and the
independent scientific-provider example remain. Existing documentation URLs now
explain migration. Original videos, hero artwork and page styles are preserved.

## Retained notebook authority and gates

The whole exporter and configuration move to the declared `apizr.notebooks`
domain. The exporter source is identical except for its configuration import.
No notebook execution, generated contract or transformed-source rewrite is added.
Eighteen pre-move cases in `tests/fixtures/notebooks/exporter` preserve exact input,
nbconvert output and Black output hashes, tag selection and the magic refusal.
Shared modern compiler characterization JSON stays at its original path.

The architecture inventory has zero historical package kinds; their naming and
generic-bucket exemptions are removed. A negative test rejects restoring that kind.
No root implementation or migration exception is introduced. Only the deleted
tree's 59.5% coverage step is removed. The global 90% floor, modern package floors,
selected evidence line/branch gates and all 172 security mutations remain.

The `legacy` extra and the unused `questionary` development requirement are removed.
`questionary` 2.1.1 leaves the universal lock and its exact license evidence is
removed. Jinja2 remains needed by modern notebook/documentation tools; its reviewed
development security floor is retained.
The remaining notebook/HTTP/MCP/clients/preparation extras retain their roles;
the base installation still has exactly five Pydantic-related dependencies.
Homebrew's development lock binding is refreshed without changing any of its six
build wheels, the published manifest or historical physical-host evidence.

## Installed and real-runtime qualification

The fresh wheel/sdist are checked against current metadata, README, license,
required runtime resources and absence of all three retired trees. `artifacts.json`
records SHA-256 identities and the comparison to the preceding candidate.

The installed wheel is exercised outside the checkout: IR/readiness, notebook
inspection, direct/governed REST/MCP, repository exposure and scientific providers.
Separate environments qualify base, clients, notebook, HTTP and MCP installs,
including real HTTPS/SSH source journeys and experiment notebook run/exposure.
A separately installed trusted plugin invokes successfully while a full snapshot
proves the core environment unchanged. These proofs create their own environments.

The existing four-target container matrix now generates a modern notebook REST
bundle and uses an explicit qualification Dockerfile. The local Python 3.12 Linux
container serves health and POST `/capabilities/total` = 36 as a non-root user;
its exact image identity is checked and its own container/image removed. Actual
modern resource/dependency and OCI plugin journeys remain separate existing gates.

`qualification.json` retains test, coverage, mutation and structural results.
The strict HTML check validates all 127 pages, links, anchors, canonicals and home
assets. No publication workflow or stable-branch protection is changed.

## Test results and correction scope

The common run completed in 372.88 seconds: 7,568 passed and 74 expected platform/
explicit-worker-image skips. Six failures identified the deleted-path fixture
reader, retired empty-CLI assertion and four stale development Homebrew bindings.
Those boundaries were corrected and qualified with 63 passing focused tests,
including the new architecture rejection. The broader affected set passed 575
tests; the final graph/license/Homebrew binding set passed 105. The common suite
was not repeated after these scoped corrections. CI reruns the exact
committed tree across the existing platforms and interpreter matrix.

Combined branch-aware coverage is 97.46%; all 22 required compatibility coverage
checks pass, including selected evidence line/branch gates. All 172 mutants are
killed after a 470-test baseline. Ruff, Pyright, architecture, pre-commit and the
strict 127-page HTML checks pass. The preceding source's CI completed with 80
successful jobs, without failure.
