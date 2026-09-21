# Publishing a release

This is the maintainer procedure. Users should follow [Start here](../getting-started/introduction.md)
and the [compatibility guide](../getting-started/developer-guide/releases.md).

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

1. Prepare a PR with current README, release notes, compatibility guidance and package
   metadata. `pyproject.toml` is the version source; installed application/CLI
   versions come from distribution metadata. Keep `0.2.0` for this release.
2. Merge through the protected default branch after **all** required checks pass.
   Wait for CI, Security and Documentation to pass again on the exact master
   merge commit. Do not disable a gate, lower a coverage floor or use an admin bypass.
3. From that successful **master push CI run**, download `python-distributions`
   and `distribution-checksums`. The package job builds wheel/sdist once, inspects
   their metadata and contents, and tests the same wheel outside checkout on
   Python 3.11 and 3.14, including the README example and legacy/modern workflows.
   The separate required OCI job builds its own test image; it verifies the same
   source revision, not byte identity with the publication artifact.
4. Review the actual archived README/metadata and hashes. Optionally run
   `uvx twine check --strict dist/*` locally. Preserve the CI run ID and commit SHA
   in the release record. Never rebuild on a laptop for the upload.
5. Check [PyPI release history](https://pypi.org/project/outerspace-apizr/#history)
   immediately before publication. Versions and filenames are immutable. If
   `0.2.0` already exists, stop and investigate; do not overwrite, silently skip
   files, or automatically choose another version.
6. Create `v0.2.0` on that exact verified merge commit. Release tags are protected
   against deletion/force updates. Prepare the GitHub release notes from
   [0.2.0](../releases/0.2.0.md) and attach the reviewed wheel/sdist and checksums.
7. Explicitly dispatch **Publish PyPI** on the tag, passing the verified master
   `ci_run_id`. Its verification job checks tag/version/commit, successful CI,
   Security and Documentation runs, availability of the PyPI version, archive
   metadata and original checksums. It downloads and forwards the same bytes;
   there is no rebuild. Approve the protected `pypi` deployment after review.
8. The isolated publication job downloads the verified artifacts and exchanges
   its GitHub identity with PyPI using the pinned PyPA action. Only this job has
   `id-token: write`; it does not check out or execute repository source. A
   failed/partial upload requires inspection of PyPI state before any retry.
9. Verify PyPI metadata, rendered README and file SHA-256 values against the
   reviewed artifacts. Install `outerspace-apizr==0.2.0` from PyPI in a fresh
   environment outside checkout and run the CLI/example smoke. Record the actual
   publication date, release links and hashes; update the changelog's `Unreleased`
   label through a follow-up documentation PR if publication has completed.

Example deliberate dispatch, after the tag exists and checks are green:

```sh
gh workflow run publish-pypi.yml --ref v0.2.0 -f ci_run_id=REVIEWED_MASTER_RUN_ID
```

Publication is never triggered by an ordinary master push or PR. The workflow
must be present on the default branch before its first manual dispatch.

## Release checklist

Complete against the final commit; historical green runs are not sufficient.

- [ ] Version, tag and built metadata agree; target version is unused on PyPI.
- [ ] README renders, public URLs work and current/legacy documentation is accurate.
- [ ] Ruff, Pyright and pre-commit pass.
- [ ] Python 3.11–3.14 tests and every package coverage floor pass.
- [ ] Wheel/sdist content and hashes are reviewed; installed-wheel smoke passes.
- [ ] Legacy container matrix and mandatory `oci-isolation` pass unchanged.
- [ ] Dependency audit, CodeQL and strict MkDocs build pass.
- [ ] Open issues are classified and no release blocker remains unresolved.
- [ ] Ownership, Trusted Publisher and protected `pypi` environment are verified.
- [ ] The tag identifies the exact verified master commit and CI artifact run.
- [ ] PyPI file hashes and fresh index installation are verified after publication.

## Documentation publication

Documentation is independent of PyPI. PRs run a strict MkDocs build. A master
push builds and publishes the site to `gh-pages`, served at
[apizr.outerspace.sh](https://apizr.outerspace.sh/). Keep this active publication
branch; edit Markdown and MkDocs configuration, not generated files.

## Repository protections

Apizr follows the same protection model as `Alien6-Studio/continuum-attest`:
PR-only changes, no force push/deletion or bypass actors, signed commits on the
default branch, resolved review threads, and required up-to-date checks. GitHub
squash merging provides a verified merge commit. All 14 existing Apizr gates
remain required, including `oci-isolation`; their names and floors are unchanged.

GitHub Actions defaults to read-only permissions and cannot approve PR reviews.
Individual deployment jobs explicitly declare necessary write permissions.
Release tags cannot be deleted or force-updated. CODEOWNERS requests maintainer
review of external contributions; as with the reference repository, mandatory
independent PR approval remains zero while there is one active owner. This is
not a claim of independent human review. The publication environment has a
separate maintainer approval gate. Dependabot reviews uv and Actions updates.

Secret scanning, push protection, dependency security updates and private
vulnerability reporting remain enabled. None substitutes for source review.

## Site analytics review

The existing Google Analytics property `G-P3BHZB2FVP` and Material cookie-consent
configuration are retained; no tracker was added. Their original business purpose
and account ownership cannot be established from source alone. The maintainer
should confirm continued use and property ownership. The consent text describes
repeat visits/preferences and documentation usage; Material gates configured
analytics on consent. This release removes obsolete decorative/social templates,
not analytics by assumption.
