# Pending master reconciliation for PR #346

Development: `0.4.6`; stable source: `b7c576d9b26c3c55027d0efeff253ab7f4aa73aa`.

The maintainer explicitly approved this development-only reconciliation on
2026-10-16. All 54 overlapping paths are resolved against development source
`98377601ef1812d0ca3dacb39f5fe35299c25058`. The earlier automatic approval rejection
was resolved by that authorization; it did not change any branch or file.

The result preserves the 0.4.6 product/metadata/security/CI work and integrates
the stable reader paths, architecture diagrams, example downloads, publication
history and isolated documentation environment. Qualification tools remain in
canonical domains with forwarding entrypoints. All development navigation pages,
original video IDs, hero bytes and the 759 historical anchors remain available.
Forty-seven compatibility anchors restore links renamed during 0.4.6 work.

The docs lock reuses only versions, source URLs and archive hashes already
reviewed in the root lock, including Ruff 0.17.0. Neither root uv.lock nor any
production implementation under src/, plugin src/ or VS Code src/ changes.
The site marker remains release-candidate, target 0.4.6, stable 0.4.5; no new
publication authorization, tag, release or stable-branch update is introduced.

Validation: 170 tests in the isolated documentation environment without Apizr
installed; 518 affected architecture/packaging/CI/Attest tests; strict construction
and HTML validation of 160 pages and all baseline anchors. The three actual
Markdown scenarios pass with an installed candidate outside checkout, including
REST/MCP, closed inputs, useful refusals and Python compiler parity. The exact
README, migration, TypedDict and current/historical Quickstarts also pass.
The source-free quote delivery fixture builds both interfaces and removes its
original project. Ruff, Pyright, actionlint and pre-commit gates pass. Native
Mermaid pre/code output and consent-aware GitHub repository metadata are retained.
The 49 integrated upstream non-merge commits pass the actual DCO validator.

Full exact-source hosted qualification belongs to the PR and development push
created by this merge. No merge of PR #346 into master or publication is authorized
by this reconciliation.

Conflicted paths requiring review:

- `.github/workflows/ci.yml`
- `.github/workflows/mkdocs.yaml`
- `CHANGELOG.md`
- `Dockerfile`
- `README.md`
- `SECURITY.md`
- `action.yml`
- `docs/architecture/capability-graph-v1.md`
- `docs/architecture/exposure-plan-v1.md`
- `docs/architecture/repository-bundle-v1.md`
- `docs/architecture/repository-readiness-v1.md`
- `docs/assets/stylesheets/branding.css`
- `docs/contributing/release-branches.md`
- `docs/contributing/releases.md`
- `docs/contributing/verification.md`
- `docs/development/0.4.md`
- `docs/getting-started/data-science.md`
- `docs/getting-started/developer-guide/releases.md`
- `docs/getting-started/developer-guide/setup.md`
- `docs/getting-started/install.md`
- `docs/getting-started/introduction.md`
- `docs/getting-started/quickstart.md`
- `docs/getting-started/user-guide/ci-integrations.md`
- `docs/getting-started/user-guide/client-collections.md`
- `docs/getting-started/user-guide/experiment-exposure.md`
- `docs/getting-started/user-guide/experiment-inspection.md`
- `docs/getting-started/user-guide/experiment-runs.md`
- `docs/getting-started/user-guide/exposure.md`
- `docs/index.md`
- `docs/reference/apizr-mcp-server.md`
- `docs/reference/attest-delivery-plugin.md`
- `docs/reference/oci-service-plugin.md`
- `docs/reference/plugin-catalog.md`
- `docs/reference/plugin-preparation.md`
- `docs/releases/0.4.5.md`
- `examples/data-science/fraud-detection/README.md`
- `mkdocs.yml`
- `plugins/attest/README.md`
- `plugins/mcp/README.md`
- `plugins/oci/README.md`
- `scripts/check_docs_html.py`
- `scripts/check_docs_site.py`
- `scripts/ci_scope.py`
- `scripts/coordinated_distributions.py`
- `scripts/delivery_source_proof.py`
- `scripts/docs_build.py`
- `scripts/smoke_oci_plugin.py`
- `scripts/smoke_oci_registry.py`
- `scripts/smoke_readme.py`
- `templates/apizr.yml`
- `tests/ci/test_forges.py`
- `tests/test_ci_scope.py`
- `tests/test_dco.py`
- `tests/test_docs_publication.py`
