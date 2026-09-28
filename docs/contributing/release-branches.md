# Release branches and qualification

`master` is the last integrated qualified release baseline. All 0.4.1 development
uses **`release/0.4.1`**, created from master
`89678f1fa525c98b2b60096536f613bde033304d`. Creating this line changes no product
state and does not create a release candidate. The governance PR targets this
line, not master; it must not be merged as part of the setup task.

## Branch and version lifecycle

1. Create short-lived feature/fix branches from `release/0.4.1`, for example
   `feature/application-dependencies`, `feature/delivery-manifest`,
   `feature/mandatory-proof` or `fix/...`. Their PRs target `release/0.4.1`.
2. Keep each feature separately scoped and checked. These examples are future
   scope, not features implemented or issues opened by this governance change.
3. Prepare coordinated versions only for an actual release candidate. All four
   projects currently retain **0.4.0rc1**; branch creation requires no version bump.
   Builds with that inherited version are verification evidence only, not the
   published RC bytes or a new publication authorization.
4. After explicit candidate preparation, qualify the exact release-line push
   commit and original artifacts. Create immutable **tags/releases** `v0.4.1rc1`,
   `v0.4.1rc2`, etc. only when separately authorized. RCs are not long-lived branches.
5. Qualify final `v0.4.1` on the release line and follow the controlled
   [publication procedure](releases.md#release-procedure).
6. Only after final qualification/publication integrate the final state into
   `master` through its protected PR process and checks. A squash integration
   creates a different commit: record both identities and verify the resulting
   baseline; never move the release tag or substitute rebuilt distributions.
7. Only then create `release/0.4.2`. It does not exist as part of this transition;
   enabling its qualification requires a future explicit policy change.

The trajectory is **0.4.0rc1 → 0.4.1rc1 / rc2 … → 0.4.1 → 0.4.2**.
There will be no new final 0.4.0. Historically the core 0.4.0 reached PyPI but
coordinated publication failed; that version was superseded/removed. The corrected
coordinated 0.4.0rc1 is published and immutable. Do not rebuild its published
artifacts, retag, republish or modify it. The updated publication verifier rejects
both closed 0.4.0 versions; historical evidence verification remains possible.

## Audit before changes

The [audit issue #186](https://github.com/Alien6-Studio/outerspace-apizr/issues/186)
records the pre-change inspection on 28 September 2026. Master was exactly the
source SHA above, with successful push CI `36456323738`, Security `36456323741`
and Documentation `36456323667`. The working tree was clean. Only `master` and
`gh-pages` existed remotely; no issues or PRs were open. The new release branch
initially points to that same SHA. No functional 0.4.1 work was assumed.

All repository workflows were inspected:

| Workflow | Existing branch assumptions | Governance result |
| --- | --- | --- |
| `ci.yml` | Push on master/develop; unrestricted PRs; master-only provenance | Add explicit release/0.4.1 push validation; sign release-line evidence only when `github.ref_protected`; pass exact source ref to asset staging |
| `security.yml` | Master pushes, all PRs, default-branch weekly schedule/manual | Add explicit release/0.4.1 pushes; keep schedule/manual behavior |
| `mkdocs.yaml` | Master pushes/all PRs/manual; deployment and queued-source check require master | Add release-line validation; preserve both master deployment guards |
| `publish-pypi.yml` | Manual only; successful master push artifacts and master provenance | Version-bound release-line source ref; same protected tag dispatch, receipt/publisher approvals and original-byte checks |
| `oci-service-plugin.yml` | All PRs/manual; disposable image/registry qualification | Unchanged; already validates release-targeted PRs |
| `attest-delivery-plugin.yml` | All PRs/manual; disposable signed delivery/OCI proof | Unchanged; already validates release-targeted PRs |
| `mcp-server-plugin.yml` | All PRs/manual; real stdio/catalog/install/uninstall matrix | Unchanged; already validates release-targeted PRs |
| `extension-packaging.yml` | All PRs/manual; uv and local-only Homebrew prototype | Unchanged; no public tap publication |
| `extension-cleanup.yml` | All PRs/manual; repeated disposable cleanup proofs | Unchanged; no release mutation |

Other assumptions found:

- `verify_release.py` required exact successful master push CI, Security and
  Documentation runs. Now 0.4.1 RC/final versions require `release/0.4.1` for all
  three, the same SHA/repository, and actual branch protection. Arbitrary branches,
  PR runs, other release lines and newer failed verification runs remain rejected.
- `prepare_release_assets.py` and publication provenance pinned `refs/heads/master`.
  Staging now binds the exact allowlisted source ref; publication consumes the
  verifier's output, never an unchecked branch input. PR staging remains a preview.
- Release verification/asset tests contained master literals; historical cases
  retain them, and release-line positive/negative cases cover the new binding.
- Contribution, release, verification and development checkout guides assumed
  direct master development. They now describe the release line. The completed
  `publish-0.4.md` procedure is explicitly archival and must not be replayed.
- README badges, baseline source/example links, historical release notes, published
  0.4.0rc1 install/provenance commands and frozen 0.3 fixtures legitimately retain
  master references. Documentation deployment's master check is intentionally retained.
  `scripts/docs_build.py` still identifies the published 0.4.0rc1 baseline; no
  version marker is promoted. Product Git-source default-branch refusal and the
  external Moby master link are unrelated to release governance.
- Dependabot has no `target-branch`, so it uses the default branch. Its active
  configuration is read from master: this PR cannot reroute it by changing only
  a release branch. Until an explicitly authorized default-branch configuration
  change, recreate/retarget dependency-update work against `release/0.4.1` and do
  not merge next-release dependency changes directly into master. Default CodeQL
  setup (Python/Actions, weekly) and other default-branch schedules remain intact.

Branch creation itself does not match the baseline workflows' push filters.
After this PR is merged, release-line pushes produce validation artifacts and,
only with actual protection, signed build evidence. They never create tags,
GitHub releases, PyPI packages, production registry artifacts or stable docs.
The existing PyPI workflow is already present on master for manual dispatch;
a future authorized release tag selects its reviewed release-line version.
The `archive-evidence` job uploads only after manual publication verification.
No new workflow, secret, environment or registry is introduced.

## Actual protections detected

At this audit, master is protected by active ruleset **23727291**,
[Protect default branch](https://github.com/Alien6-Studio/outerspace-apizr/rules/23727291),
which targets only `~DEFAULT_BRANCH`. The legacy branch-protection endpoint returns
404; this does not mean master is unprotected. Effective rules are:

- PR required, stale approvals dismissed, review threads resolved, zero required
  approving reviews, no required code-owner/last-push approval; extra approval for
  unattributed changes enabled. No independent human review is claimed.
- Signed commits, no deletion or force updates, no bypass actors.
- Strict up-to-date status checks from GitHub Actions app **15368**: `quality`,
  `compatibility (3.11)`, `compatibility (3.12)`, `compatibility (3.13)`,
  `compatibility (3.14)`, `package`, `container (3.11)`, `container (3.12)`,
  `container (3.13)`, `container (3.14)`, `build`, `dependencies`, `codeql`,
  `oci-isolation`, `security-mutations`, `macos (3.11)`, `macos (3.14)`.
- Ruleset permits merge/squash/rebase, but repository settings permit **squash
  only**. DCO author sign-off is enforced in the existing `quality` job; it is
  distinct from cryptographic signing. CODEOWNERS remains unchanged.

**`release/0.4.1` is not protected by that ruleset.** Its effective rules are empty
at creation. Running these checks or checking in proposed rules is not protection.
The governance task does not modify repository protections.

The separate active `Release tags` ruleset protects `v*` from deletion/force update.
The `pypi` environment allows only tags `v*`, requires Coopyrightdmin approval,
allows self-review and forbids administrator bypass. `github-pages` permits only
master/gh-pages; the deployment workflow independently requires a master push.
Actions default to read-only and cannot approve PR reviews. These settings are
unchanged; release-line branches must not be added to production environments.

## Required maintainer action

Before merging development or qualifying a release on the line, configure an
**additional active branch ruleset** targeting exactly `refs/heads/release/0.4.1`,
with no excludes or bypass actors and all master rules/checks above. Do not alter
or remove the existing master/tag rulesets. Preserve squash-only repository merge
settings and existing deployment restrictions.

The exact proposed API payload is checked in at
[`.github/release-0.4.1-ruleset.json`](https://github.com/Alien6-Studio/outerspace-apizr/blob/chore/release-0.4.1-branching/.github/release-0.4.1-ruleset.json).
It is **not applied automatically** and does not claim enforcement. A maintainer
must explicitly authorize applying it, then verify the effective branch rules and
required checks through GitHub before merge. This task has admin capability but
no authorization to mutate protections. No bypass is used.

All current mandatory checks retain their names and thresholds. Additional
candidate-target/delivery/asset jobs remain required by successful overall release
CI and the publication verification procedure, rather than being falsely listed
as already-required branch status checks. No final integration, version promotion,
release tag or publication is authorized by this document.
