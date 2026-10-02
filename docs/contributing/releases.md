# Publishing a release

This is the maintainer procedure. Users should follow [The full journey](../getting-started/introduction.md)
and the [compatibility guide](../getting-started/developer-guide/releases.md).

## Current published baseline

The current stable release is **0.4.3** for the core and all three plugins,
source `cfaa5108c37ab9324297bbe5b38d90d537ea57ad`. Publication is complete.
The original archives from protected release-line CI `37057658519` were published
by workflow `37062660371`; all eight public files match the qualified bytes.
See the [release record](../releases/0.4.3.md). Master integration and documentation
commits preserve the released product but never replace its immutable source.
Documentation maintenance targets `master`.

The **0.4.1rc1** and **0.4.0rc1** prereleases remain immutable history. The earlier
core-only 0.4.0 upload was incomplete and removed; no coordinated final 0.4.0
exists. **RC2 NOT REQUIRED:** the 0.4.1 finalization changed versions and
documentation without changing runtime behavior, and the final archives were
independently qualified and publicly verified.

The immutable `v0.4.2rc1` prerelease was published and verified from
`e8bd1166eff98a3766ec586c6a36c2f58ac14853`; publication #231 is complete.
Corrective `0.4.2rc2` was qualified at
`3e58c7969129e368a21f8188b12c94ab3059b421` after the first final qualification
exposed a worker-pipe cleanup failure. PR #234 fixes pipe closure on cleanup errors.
Final `0.4.2` is published with no runtime or third-party dependency change from
that qualified RC2. Tracking #232 retains the failed run, corrective qualification,
exact final source and verified publication evidence.
See the [0.4.2 release record](../releases/0.4.2.md).

## Completed 0.4.3 qualification

The coordinated **0.4.3** core and all three plugins are published and verified.
The [release record](../releases/0.4.3.md) identifies the exact protected source,
successful qualification and publication runs, and public-byte comparison.
The original four wheels, four sdists, target exports, delivery evidence and
signed provenance remain immutable. Do not replay qualification or package
publication for this completed release. PR builds remain previews.

Official MCP Registry publication is independent of the package workflow.
After master integration, manually dispatch `Publish MCP Registry` for `v0.4.3`
and its recorded source SHA. It verifies the public release and matching
`server.json`, then authenticates with the repository's GitHub Actions OIDC
identity. The public PyPI launcher and package ownership marker have passed
validation. No personal token or rebuild is required.

## Retain and publish one coordinated artifact set

CI builds four wheels and four sdists once per candidate. Independent sdist
reconstructions are tests and never replace the selected archives. Retain
`release-candidate`, the six `release-target-*` exports, `release-delivery`,
`build-attestations` and `release-assets`. The latter is only an Actions artifact,
not an automatic upload to a GitHub release. PR previews lack signed provenance
and cannot authorize publication.

The completed 0.4.1 qualification selected the successful protected
**release/0.4.1 push** run on the exact source commit, plus successful Security
and Documentation runs on that same branch and commit. The signer recorded
that protected ref in the retained evidence. The old branch can be retired
without changing that evidence identity.

The publication verifier accepts exactly `0.4.3` from protected `release/0.4.3`
and rejects unintended versions and refs. It must not be used to replay this
completed release. Historical verifier versions retain their original policies. New development builds do not authorize a
publication. Releases through 0.4.0rc1 retain `master` provenance; published
0.4.1 retains `refs/heads/release/0.4.1` provenance.

Qualification includes Linux CPython 3.11–3.14, macOS 3.11/3.14 and disposable
registry/TSA/ORAS fixtures. Target reports record architecture, patch version,
bytes and timing samples. Runtime SBOM attestations cover the core distributions;
plugin dependency identities remain in target inventories. Disposable worker
image identities are test evidence, not official published images.

Publication stays manual and requires explicit authorization of the exact
version, source, CI run and original hashes. Trusted Publishing must be configured
for all four projects. The workflow uploads **core → OCI → MCP → Attest**,
requires separate protected receipt/publication approvals, and compares downloaded
public archives with the original eight files. Existing bytes must match exactly;
missing files alone are staged. No rebuild, overwrite or `skip-existing` is allowed.
Network/access errors never mean absence. Verify fresh public installations and
retain the public comparison and signed timestamped receipt before declaring delivery.

For first-time plugin publishers, PyPI allows only one pending publisher for an
identical repository/workflow/environment configuration. Register and publish one
package at a time using the exact `package` input, then finish with `package: all`
to archive release-wide evidence. These prerequisites do not authorize a new upload.
Completed 0.4.0rc1, 0.4.1rc1, 0.4.1, 0.4.2rc1, 0.4.2 and 0.4.3 deliveries must not be dispatched again.

## Published 0.3.0

**0.3.0 was published on 22 September 2026** from commit
`43f5626fe9e26b018aa323abd83b9611f7b2aba9`, tagged `v0.3.0`.
Publication reused the exact master CI `35735875051` distributions. The managed
receipt and Trusted Publishing workflow passed; public PyPI bytes were compared
with the CI files. See the [release record and hashes](../releases/0.3.0.md#verified-delivery).
Keep this tag and its distributions unchanged. The protected procedure below applies
to a future explicitly authorized release.

## Published releases and verification builds

**0.2.0 was published on 21 September 2026**, from commit
`31997407010d6e38f99970d0b3b319135a0d5d15`, tagged `v0.2.0`.
Keep that tag and its PyPI/GitHub distributions unchanged. See the
[release notes](../releases/0.2.0.md) for the shipped scope.

The later commits that still declared `0.2.0` produced verification artifacts:
sharing a version number did not make them the published files, and they must
not replace those files. **0.2.1 was published on 21 September 2026**, from
`8ab471de436b1ca92a3b213c40402c5241926d5a`, tagged `v0.2.1`.
Its [maintenance notes](../releases/0.2.1.md) record the verified delivery and
signed timestamped receipt. Keep its tag and distributions unchanged too. Build attestations
apply only to their exact subjects and source commit.

The procedure below is for a future **explicitly authorized release**. Prepare
each new version through a separate release PR; version metadata alone does not
mean publication has occurred. Published historical versions remain immutable.
Recovery of a partial coordinated publication requires the original approved
archives and exact comparison; it never permits replacing public bytes.

<span id="pypi-ownership"></span>

## Ownership and one-time setup

Verify **Owner** access to the existing `outerspace-apizr` PyPI project. Do not
rename/recreate it because an organization was removed; individual project
permissions and organization membership are separate.

Configure a [PyPI Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
for the existing project, with these exact fields:

| Field | Value |
| --- | --- |
| GitHub owner | `Alien6-Studio` |
| Repository | `outerspace-apizr` |
| Workflow filename | `publish-pypi.yml` |
| Environment | `pypi` |

The GitHub `pypi` environment must require maintainer review and allow only release
tags matching `v*`. Publishing uses OIDC, not a stored PyPI token. A workflow file
alone does **not** establish PyPI ownership or configure this trust relationship;
verify the publisher in PyPI before dispatching. TestPyPI is a separate service
and publisher and is not part of this workflow.

## Release procedure

The steps below record the completed **0.4.1** procedure and its original source
line. Do not replay publication after retiring that branch. Qualification and
publication of 0.4.2 use the reviewed `release/0.4.2` version/ref policy;
creating a branch alone does not authorize publication.

1. Prepare a PR with current README, release notes, compatibility guidance and package
   metadata. `pyproject.toml` is the version source; installed application/CLI
   versions come from distribution metadata. Use the explicitly authorized,
   previously unpublished version; align its release notes and changelog.
2. Merge the candidate preparation PR into protected `release/0.4.1` after
   **all** required checks pass. Wait for CI, Security and Documentation to pass
   again on that exact release-line merge commit. Do not integrate into `master`
   yet. Do not disable a gate, lower a coverage floor or use an admin bypass.
3. From that successful **release/0.4.1 push CI run**, download `python-distributions`
   and `distribution-checksums`, plus `release-candidate`, every `release-target-*`
   export and `release-delivery`. The distributions job builds all eight archives
   once. Target jobs install those exact wheels outside checkout. OCI jobs build
   their disposable images from the retained core/plugin wheels; image identities
   and package hashes describe different artifacts.
4. Review the actual archived README/metadata and hashes. Optionally run
   `uvx twine check --strict dist/*` locally. Preserve the CI run ID and commit SHA
   in the release record. Never rebuild on a laptop for the upload.
5. Check [PyPI release history](https://pypi.org/project/outerspace-apizr/#history)
   immediately before publication. Versions and filenames are immutable. If
   the target version already exists, inspect it. The coordinated recovery path
   accepts only byte-identical approved files; never overwrite, silently skip files,
   or automatically choose another version.
6. Create `v<version>` on that exact verified merge commit. Release tags are protected
   against deletion/force updates. Prepare the GitHub release notes from
   the reviewed notes for that version and attach the eight reviewed archives, checksums and target exports.
7. Explicitly dispatch **Publish PyPI** on the tag, passing the verified release-line
   `ci_run_id`. Its verification job checks tag/version/commit, successful coordinated CI,
   Security and Documentation runs, public artifact state, archive
   metadata and original checksums. It downloads and forwards the same bytes;
   there is no rebuild. Approve the protected `pypi` receipt job after review.
8. The receipt job signs and RFC 3161 timestamps those exact distributions and
   evidence with the managed Apizr identity. Signature, expected identity,
   timestamp and recomputation must all pass; missing keys or timestamp service
   failures stop delivery. Review its receipt before approving the protected
   publication job. The isolated publication job downloads the verified artifacts and exchanges
   its GitHub identity with PyPI using the pinned PyPA action. Only this job has
   `id-token: write`; it does not check out or execute repository source. A
   failed/partial upload requires inspection of PyPI state before any retry.
9. Verify PyPI metadata, rendered README and file SHA-256 values against the
   reviewed artifacts. Install `outerspace-apizr==<version>` from PyPI in a fresh
   environment outside checkout and run the CLI/example smoke. Record the actual
   publication date, release links and hashes; update the changelog's `Unreleased`
   label through a follow-up documentation PR if publication has completed.

Example deliberate dispatch from the verified release checkout, after the new
tag exists and checks are green. Set `REVIEWED_RELEASE_RUN_ID` to the reviewed
successful release-line push CI run ID. **Never dispatch the closed 0.4.0 or
already-published 0.4.0rc1 delivery.**

```sh
RELEASE_VERSION=$(python -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])')
gh workflow run publish-pypi.yml --ref "v${RELEASE_VERSION}" \
  -f release_tag="v${RELEASE_VERSION}" -f ci_run_id="$REVIEWED_RELEASE_RUN_ID"
```

Publication is never triggered by an ordinary branch push or PR. The workflow
must be present on the default branch before its first manual dispatch.

## Release checklist

Complete against the final commit; historical green runs are not sufficient.

- [ ] All four versions, tag and built metadata agree; public files are absent or byte-identical to the approved set.
- [ ] README renders, public URLs work and current/legacy documentation is accurate.
- [ ] Ruff, Pyright and pre-commit pass.
- [ ] Python 3.11–3.14 tests and every package coverage floor pass.
- [ ] Wheel/sdist content and hashes are reviewed; installed-wheel smoke passes.
- [ ] Legacy container matrix and mandatory `oci-isolation` pass unchanged.
- [ ] Dependency audit, CodeQL and strict MkDocs build pass.
- [ ] License inventory/policy and preserved notices cover the exact universal lock.
- [ ] Open issues are classified and no release blocker remains unresolved.
- [ ] Ownership, Trusted Publisher and protected `pypi` environment are verified.
- [ ] The tag identifies the exact verified release-line commit and CI artifact run.
- [ ] Managed Attest identity, signature, RFC 3161 timestamp and recomputation pass
      for the exact delivery; receipt and public verification material are archived.
- [ ] PyPI file hashes and fresh index installation are verified after publication.

## Documentation publication

Documentation is independent of PyPI and follows `master`; it is not a frozen
versioned documentation site. For the exact published source documentation, use
the [v0.3.0 tag](https://github.com/Alien6-Studio/outerspace-apizr/tree/v0.3.0/docs).
Release notes distinguish shipped behavior from subsequent maintenance.
Material's native repository component displays the latest GitHub release tag,
stars and forks using `repo_url` and `repo_name`. On desktop it appears beside
the search bar; on mobile it appears in the navigation drawer. GitHub requests
remain subject to the site's optional GitHub consent setting. No release number
is hard-coded in the theme, and no header override is needed. See
[Material's repository documentation](https://squidfunk.github.io/mkdocs-material/setup/adding-a-git-repository/).

PRs and protected release-line pushes run strict MkDocs and HTML validation without
deployment. Stable documentation still follows the integrated baseline. A master
push builds and publishes the site to `gh-pages`, served at
[apizr.outerspace.sh](https://apizr.outerspace.sh/). Keep this active publication
branch; edit Markdown and MkDocs configuration, not generated files.

The generated `build-info.json` records the full **source** commit, whether the
checkout was dirty, publication status, stable release and fingerprints of the
home page, Git/OCI/Attest pages and home assets. The footer links to it. It is not
the generated `gh-pages` commit; no source hash is maintained by hand. A local
dirty build is a preview and cannot pass publication confirmation.

The workflow checks four distinct stages: strict construction and HTML validation,
`gh-deploy`, the GitHub Pages build for the generated commit, then exact content
served over HTTPS. The final check requires the expected marker and matching page
and asset hashes, not just HTTP 200. TLS and hostname validation remain enabled;
redirects are refused. Probe subprocesses bound DNS, connection and body reads;
responses are capped at 8 MiB and propagation at 600 seconds total. Failure retains
attempt diagnostics and fails the deployment job.

Deployment plus verification is serialized without cancellation once running.
A queued job whose source is no longer `master` is explicitly reported as
superseded, not published. A different marker (including a newer source) cannot
satisfy an older job. The marker is checked again after reading pages to detect a
switch during observation. This is point-in-time evidence, not an uptime monitor.
No PR deploys; new pages remain **ready in the PR** until an authorized merge and
successful public verification. Never edit `gh-pages` directly to bypass review.

## Repository protections

The following describes the **configured master protections**. The equivalent
release-line ruleset transfers to `release/0.4.2`; see the
[active release protections](release-branches.md#actual-protections-detected).

Apizr follows the same protection model as `Alien6-Studio/continuum-attest`:
PR-only changes, no force push/deletion or bypass actors, signed commits on the
default branch, resolved review threads, and required up-to-date checks. GitHub
squash merging provides a verified merge commit. The original 14 gates remain
required, including `oci-isolation`; additional macOS and security-mutation gates
protect the expanded validation matrix. Coverage floors are documented in the
[verification guide](verification.md).

GitHub Actions defaults to read-only permissions and cannot approve PR reviews.
Individual deployment jobs explicitly declare necessary write permissions.
Release tags cannot be deleted or force-updated. CODEOWNERS requests maintainer
review of external contributions; as with the reference repository, mandatory
independent PR approval remains zero while there is one active owner. This is
not a claim of independent human review. The publication environment has a
separate maintainer approval gate. There is one active maintainer: self-review of
publication remains possible, and no independent source review is claimed. Branch
bypass rules and environment administrator bypass are separate settings.
Dependabot proposes uv and Actions updates for review.

Secret scanning, push protection, dependency security updates and private
vulnerability reporting remain enabled. None substitutes for source review.

## Site analytics review

Google Analytics was removed for 0.2.1 after the maintainer's decision in #73.
The site no longer has an Analytics provider or property configured. Optional
GitHub statistics remain unchecked by default. The consent panel provides accept,
reject and settings controls, and the footer exposes a persistent **Cookie settings**
link. Verify a clean browser and a previously stored Analytics opt-in: neither
should load Analytics. Test rejection and explicit GitHub opt-in separately.
The original hero and bee logo remain part of the site. Google Fonts makes
separate requests; the optional consent controls apply to GitHub statistics.

## Additional evidence for future releases

Before publication, download and inspect `build-attestations` from the exact CI run
and `dependency-audit` from its verified Security run. The publication workflow
requires valid signed provenance for the wheel, sdist and `ci-evidence.tar.gz`, then
preserves the evidence on the existing GitHub release. See the
[verification guide](verification.md) for contents, commands and limitations.
Never attach a later build's attestation to the original 0.2.0 files as if it were
produced by the original build. Never replace the original distributions or tag.

## Social link previews

The site serves a static 1200 × 630 PNG at
[`assets/images/social-card.png`](../assets/images/social-card.png). All pages include
[Open Graph metadata](https://ogp.me/) and a Twitter large-image card in their HTML
head, with the page title, description and absolute canonical URL. The homepage uses
the same metadata through its custom layout. Crawlers do not need JavaScript, cookies
or an authenticated request to read the metadata or image.

After deployment, verify the homepage and a nested documentation URL, then use
[LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) for links that
LinkedIn has already cached. Other networks also control their own preview caches.
