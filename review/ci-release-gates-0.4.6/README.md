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

The corrected hosted CodeQL job 117029415228 in run 38917596171 passes and
retains Python, JavaScript and Actions SARIF. The report records exact identities
and findings; a successful scan is not a zero-findings claim. CodeQL recreates
its output directory, so selection metadata is retained in a separate directory
with a regression test. Native exports already carry exact revision provenance;
uncovered-ref exports are additionally bound by the exact CI run/job identity.

Two JavaScript findings concern JSON embedded into generated test fixture code.
The fixtures now pass that data through a dedicated child environment variable
and parse it as JSON, avoiding code construction from serialized data. This only
changes tests; VSIX production contents are unchanged. The complete Node test
suite is run after the change; a fresh hosted scan remains the confirmation.

Two Actions findings trace the already-verified protected release SHA into the
secondary checkout used solely as metadata input in the read-only public-byte
comparison job. This job has only contents read, no registry credentials/cache
step, executes reviewed workflow tools from the first checkout, and never runs
code/imports from `release-source`. Admission validates immutable tag identity,
protected-master ancestry and successful exact-source qualification before the
SHA is exported. The regression test requires that source to remain data only.
These two potential cache-poisoning reports are retained as reviewed data-flow
warnings, without suppressing a query or changing a scanner threshold.

The first real default-branch PR qualification exposed GitHub's native identity:
its dynamic scanner analyzes `refs/pull/346/head`, not the CI's virtual merge
commit. The gate now binds that exact head analysis to the tested merge only
when both complete Git trees are identical. A different merged tree retains an
explicit scan of the merge commit; no different source is accepted. A malformed
head/commit/tree response fails closed. The PR head comes from the immutable
GitHub event, so a later push cannot substitute a newer head into an older run.

`native-pr-tree-readback.json` records a real successful readback of all three
native analyses/SARIF exports for head `c67567d7`, tested merge `f1eed8d9`, and
identical tree `24c1fc70`. The added regression cases cover changed merge content,
wrong commit identity, missing trees and absent PR heads. All 158 focused
CodeQL/lifecycle/routing tests pass. This follow-up changes qualification only;
no product source, master, release tag or publication is changed.
