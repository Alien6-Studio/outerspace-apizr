# CI and release gates for 0.4.6

The required `codeql` context reuses exact-source native Python, Actions and
JavaScript/TypeScript analyses on default/protected refs and their PRs. Other
refs retain an explicit three-language scan. Native setup and master protections
are unchanged. `native-codeql-readback.json` records a real read-only retrieval
of all three analyses and SARIF exports for stable source
`b7c576d9b26c3c55027d0efeff253ab7f4aa73aa`; the reports bind that revision.
No new scan or alert upload was started by this readback.

The metadata checker verifies the original CI candidate commit, snapshot, eight
archive identities and frozen README/Project URLs before publication. Future
public comparison downloads actual PyPI bytes. PyPI, MCP and external-directory
paths enforce the check; deleting the policy cannot skip it for new versions.
Historical 0.4.4/0.4.5 releases retain their original contract. The eight real
retained archives from clean `745bae6a` pass the new gate against that exact
checkout (`original-candidate-metadata-check.json`). This is preparation proof;
#326 retains qualification of the final protected release source and actual
post-publication execution after maintainer approval and merge.

Validation: 454 targeted metadata, candidate, publication, architecture, CI
lifecycle and CodeQL tests pass. Negative cases include same-version README
edits, changed snapshots/archives/source, missing public files, false public
digests, changed downloaded bytes, stale/failed/mismatched native analyses and
missing SARIF source provenance. Pyright has zero errors; actionlint 1.7.12,
all pre-commit hooks, both architecture gates and strict 128-page HTML checks
pass. Production runtime and publication authorization are unchanged.

Live PR supersession proof and hosted target evidence are recorded separately.
No branch merge, tag, release, package, registry, extension or site publication
was performed.
