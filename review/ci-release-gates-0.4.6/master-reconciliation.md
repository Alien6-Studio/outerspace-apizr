# Pending master reconciliation for PR #346

Development: `0.4.6`; stable source: `b7c576d9b26c3c55027d0efeff253ab7f4aa73aa`.

The read-only merge preview found 54 conflicted paths, mostly overlapping
documentation refactors and final version text. The attempted local integration
was rejected by automatic approval review before execution. No merge is active
and master has not changed. Reconciliation would modify only the development
branch, preserve its 0.4.6 product and release guards, retain the stable
documentation improvements, and require architecture, DCO, docs and CI checks
before pushing. It would not merge PR #346 or authorize publication.

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
