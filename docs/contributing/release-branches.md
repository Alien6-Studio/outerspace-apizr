# Release branches and qualification

`master` now contains the published and verified **0.4.1** baseline. The
immutable release source remains `d08b37d126957593a82784ef3ad096e3f8b4929d` on
the former `release/0.4.1` line, retained by immutable tag `v0.4.1`.
Qualification #203 and publication #204 are complete. [PR #206](https://github.com/Alien6-Studio/outerspace-apizr/pull/206)
integrated that release at `e49d5f686bc9b2c9610c7849e246594feb48c3d4`.
Documentation maintenance branches from and targets `master`. New product
development uses protected `release/0.4.2`, created from the integrated master
baseline with this documentation update; `release/0.4.1` is retired.

## Branch and version lifecycle

The completed 0.4.1 sequence was:

1. Develop bounded changes through protected PRs into `release/0.4.1`.
2. Qualify and publish immutable `v0.4.1rc1`.
3. Finalize coordinated versions and documentation. No runtime behavior changed,
   so RC2 was not required.
4. Qualify exact final source and archives from protected CI `36601712772`,
   then publish and independently verify all four packages as **0.4.1**.
5. Integrate the released state through protected PR #206 into `master`.
   The integration's only additional change makes master asset staging a
   verification preview. Publication remains bound to the original release-line
   source and archives; subsequent CI builds never replace them.

The maintainer authorized replacement of the old release branch with
`release/0.4.2`. Only the branch reference is retired: published tags, source
commits, provenance and archives remain unchanged. Rule set 24138072 transfers
the same PR, signature and required-check protections to the new line.

CI, Security and Documentation validate pushes to `release/0.4.2`. The first functional increment
sets all four packages and exact internal pins to **0.4.2rc1, development and
unpublished**. Future qualification accepts only `0.4.2rc1` or `0.4.2` from
protected `release/0.4.2`, with exact successful push CI, Security and Documentation
for the same source SHA and repository. Master, other release lines, feature
branches, PR runs, unprotected sources and newer failed runs are refused.
Historical 0.4.1 qualification remains available. Feature/PR artifacts are previews;
no tag or publication is authorized by this increment. Documentation deployment remains
restricted to `master`.

The historical coordinated **0.4.0rc1** was a prerelease. The earlier core-only
0.4.0 upload was incomplete and removed; there is no coordinated final 0.4.0.
Preserve published RC tags, notes and archives. Historical evidence verification
remains available without replaying publication.

## Historical branch-creation audit

The [audit issue #186](https://github.com/Alien6-Studio/outerspace-apizr/issues/186)
records the pre-change inspection on 28 September 2026. Master was exactly
`89678f1fa525c98b2b60096536f613bde033304d`, with successful push CI `36456323738`, Security `36456323741`
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
  At that audit, documentation still described the pre-final baseline; the
  publication update now identifies stable 0.4.1. Product Git-source default-branch refusal and the
  external Moby master link are unrelated to release governance.
- Dependabot has no `target-branch`, so it uses the default branch. Its active
  configuration is read from master: this PR cannot reroute it by changing only
  a release branch. Until an explicitly authorized default-branch configuration
  change, recreate/retarget dependency-update work against `release/0.4.1` and do
  not merge next-release dependency changes directly into master. Default CodeQL
  setup (Python/Actions, weekly) and other default-branch schedules remain intact.

Branch creation itself does not match the baseline workflows' push filters.
Release-line pushes produce validation artifacts and,
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

The default-branch ruleset does not cover release branches. The separate active
ruleset **24138072**, [release-line protection](https://github.com/Alien6-Studio/outerspace-apizr/rules/24138072),
is transferred from retired `release/0.4.1` to `refs/heads/release/0.4.2`, retaining
the same 17 required checks, signed commits, PR restrictions, deletion/force-push
prohibitions and no bypass actors. Only its name and branch target change.
Checked-in configuration alone is not enforcement; verify the live rule set.

The separate active `Release tags` ruleset protects `v*` from deletion/force update.
The `pypi` environment allows only tags `v*`, requires Coopyrightdmin approval,
allows self-review and forbids administrator bypass. `github-pages` permits only
master/gh-pages; the deployment workflow independently requires a master push.
Actions default to read-only and cannot approve PR reviews. These settings are
unchanged; release-line branches must not be added to production environments.

## Required maintainer action

Before merging development or qualifying a release, recheck the effective branch
rules through GitHub. The additional release-line ruleset is already active;
creating or changing protection is not a remaining qualification task. Preserve
master/tag rulesets, squash-only merging and deployment restrictions.

The checked-in [ruleset payload](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/.github/release-0.4.2-ruleset.json)
documents the intended configuration. It is not applied automatically and cannot
substitute for checking actual enforcement. No bypass is authorized.

All current mandatory checks retain their names and thresholds. Additional
candidate-target/delivery/asset jobs remain required by successful overall release
CI and the publication verification procedure, rather than being falsely listed
as already-required branch status checks. No final integration, version promotion,
release tag or publication is authorized by this document.
