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

Live supersession was exercised on disposable PR #347 targeting `0.4.6`.
The first rapid push (38917050872) was automatically cancelled by the second
(38917127725); the opening run (38916940713) also stopped automatically.
No cancellation request was sent for either obsolete run. Independent push
38909667156 completed successfully throughout; all 17 ruleset contexts and
master protections are byte-identical before/after. No master push was created
for this probe; its non-cancellation policy is covered by the same event-specific
concurrency tests. The final disposable run can be stopped explicitly after
observation; this does not count as automatic supersession evidence.

Hosted follow-up exposed a 403 reading default-setup settings with GITHUB_TOKEN.
That endpoint requires Administration read, which CI must not receive. Selection
now uses ordinary repository/branch metadata, then requires all three exact native
analyses for covered refs using security-events read. There is no fallback to a
successful result when an analysis is absent. The administration-only settings
readback is retained separately as operator evidence. The initial failure belongs
to run 38912125503, job 117010539006; it is not claimed as successful.

The ten Dependabot requests are consolidated in the official development line.
Python versions already qualified by run 38909667156 are black 26.10.1, FastAPI
0.143.2, Hypothesis 6.169.4, Pydantic 2.14.1 and Ruff 0.17.0. Remaining Action
references now consistently use download-artifact 8.0.2, upload-artifact 7.0.2,
setup-node 7.1.0, setup-uv 10.3.0 and CodeQL 4.38.3 (init/analyze together).
All pins are full commit identities. Publication dispatches, version allowlists
and registry authorization are unchanged. Closing the ten master-targeted bot
PRs as superseded does not claim these changes are already in master; review and
protected integration remain PR #346.
No branch merge, tag, release, package, registry, extension or site publication
was performed.
