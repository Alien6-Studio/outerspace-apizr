# Publish 0.4.0 and switch the documentation

**Preparation only: 0.4.0 is not published; stable remains 0.3.0.** This is the
handoff for the existing [manual publication workflow](releases.md), not a second
publisher. Do not execute phase B without explicit maintainer authorization.

## Available candidate resources

Audited on **28 September 2026**: master `56de041b06e0ab296955311098c8d110321ce88f`,
[CI 36339017308](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308)
and [Documentation 36339017315](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017315)
passed. [0.3.0](../releases/0.3.0.md) is the latest public release. The following
existing resources are suitable for evaluating the candidate instructions.
The revised package READMEs in this PR require **new** archives and qualification;
these older bytes must not be presented as the final replacement candidate.

| Resource | Existing CI download | Use |
| --- | --- | --- |
| Candidate and eight package identities | [release-candidate](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938660276) | Wheels, sdists, checksums, source and metadata reports |
| Linux x86-64, Python 3.11.15 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938119178) | Catalog, locked closures and qualification |
| Linux x86-64, Python 3.12.3 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938446987) | Same role, distinct target |
| Linux x86-64, Python 3.13.14 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938402295) | Same role, distinct target |
| Linux x86-64, Python 3.14.6 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938402294) | Same role, distinct target |
| macOS arm64, Python 3.11.9 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938432062) | Same role, distinct target |
| macOS arm64, Python 3.14.7 | [target](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938049440) | Same role, distinct target |
| OCI/Attest delivery | [release-delivery](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10937398875) | Disposable HTTPS, signing, timestamp and offline proofs |
| Source-bound provenance | [build-attestations](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36339017308/artifacts/10938343679) | Signed complete CI evidence and core SBOM |

Inspect the exact patch version, system, architecture and compatibility information
in each `target.json` and `qualification.json`; do not use a runner label as a
platform guarantee. Actions artifacts expire after 90 days. No `v0.4.0` release
URL is announced as available here.

## A. Before publication

1. Review the documentation/resources PR. After its authorized merge, select a
   **new exact master commit** and its successful CI, Security and Documentation
   runs. Candidate construction occurs once in `distributions`; sdist rebuilds
   are explicitly separate tests. Do not reuse the PR's candidate for that merge.
2. Use a clean checkout of that commit and set the reviewed identities:

   ```sh
   export RELEASE_COMMIT=FULL_REVIEWED_MASTER_COMMIT
   export REVIEWED_MASTER_RUN_ID=SUCCESSFUL_MASTER_CI_RUN
   test "$(git rev-parse HEAD)" = "$RELEASE_COMMIT"
   uv run --locked python scripts/verify_release.py --preflight --coordinated --source-only --run-id "$REVIEWED_MASTER_RUN_ID"
   ```

   This preflight checks the source/run and successful workflows without a tag.
   It grants no permission to publish. `--source-only` leaves public-byte checks
   to `prepare_publication.py`; it does not mean PyPI was verified.
3. Download and stage the reviewed resources without rebuilding anything:

   ```sh
   gh run download "$REVIEWED_MASTER_RUN_ID" --repo Alien6-Studio/outerspace-apizr --pattern 'release-*' --dir reviewed
   gh run download "$REVIEWED_MASTER_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name build-attestations --dir reviewed/build-attestations
   python3 scripts/prepare_release_assets.py --downloads reviewed --output approved-assets --commit "$RELEASE_COMMIT" --run-id "$REVIEWED_MASTER_RUN_ID"
   python3 scripts/prepare_publication.py --dist reviewed/release-candidate/dist --version 0.4.0 --output public-preflight
   ```

   `prepare_release_assets.py` verifies GitHub provenance of `ci-evidence.tar.gz`,
   compares the complete catalog/dependency archives and reports against its
   signed members, checks their internal file identities and copies retained
   bytes under unique names. `release-assets.json` records source, run, names,
   sizes, SHA-256 and each resource's evidence member. `SHA256SUMS` also covers
   that inventory. PR `--preview` output explicitly lacks master provenance and
   is **not** approved publication input. The CI `release-assets` job performs
   this staging automatically; it uploads only an Actions artifact.
4. Review metadata, all target reports, source/lock/license inventories and
   failure/refusal proofs. Keep the third-party notices inside the dependency
   wheels and the license/SBOM evidence inside `ci-evidence.tar.gz`. Inspect the
   public-preflight report and confirm the external prerequisites below.
5. Obtain explicit human authorization for the exact commit, run and resource
   hashes. A green PR is not release approval.

## Publication prerequisites

Read-only audit: the existing GitHub `pypi` environment requires a maintainer
review and uses the existing `v*` tag restriction. `publish-pypi.yml` is active,
manual, and retains separate receipt/publication approvals. The workflow's
presence does **not** establish PyPI ownership or trust configuration.

| PyPI project | Public 0.4.0 files at audit | Publishing rights | Trusted Publisher | Expected GitHub environment |
| --- | --- | --- | --- | --- |
| outerspace-apizr | Absent; 0.3.0 is public | **Confirmation mainteneur nécessaire** | **Confirmation mainteneur nécessaire** | `pypi` |
| outerspace-apizr-oci | Absent | **Confirmation mainteneur nécessaire** | **Confirmation mainteneur nécessaire** | `pypi` |
| outerspace-apizr-mcp | Absent | **Confirmation mainteneur nécessaire** | **Confirmation mainteneur nécessaire** | `pypi` |
| outerspace-apizr-attest | Absent | **Confirmation mainteneur nécessaire** | **Confirmation mainteneur nécessaire** | `pypi` |

For each project, confirm owner/publish rights and a publisher bound to
`Alien6-Studio/outerspace-apizr`, workflow `publish-pypi.yml`, environment `pypi`.
The available read-only access cannot verify these PyPI settings. Do not infer
that a plugin project or pending publisher exists. No token, secret, publisher,
project or protection is created by this preparation.

## Release attachment inventory

| Resource | Public attachment naming | Verification |
| --- | --- | --- |
| Four wheels and four sdists | Original exact package filenames, version 0.4.0 | Candidate SHA-256 plus build provenance |
| Candidate and attachment inventories | `candidate.json`, `release-assets.json`, `SHA256SUMS` | Candidate: signed CI evidence; derived inventory: recomputed hashes of those originals |
| Six target exports | `apizr-0.4.0-SYSTEM-ARCH-cpython-PATCH.tar.gz` | **Same bytes** as each `target-export.tar.gz`, signed evidence membership |
| Six qualification reports | Matching `apizr-0.4.0-SYSTEM-ARCH-cpython-PATCH.qualification.json` | Recorded candidate and exact target |
| Complete validation, delivery and license evidence | `ci-evidence.tar.gz` | `build-provenance.sigstore.json` |
| Core runtime SBOM binding | `runtime-sbom.sigstore.json` | Existing core wheel/sdist scope; plugin closures have target inventories |
| Release receipt and public comparison | Workflow-generated evidence after phase B | Existing Attest verification and public download comparison |

`SYSTEM`, `ARCH` and `PATCH` are read from the real reports, not typed from a runner
label: for example Linux/x86_64 and macOS/arm64 have different dependencies.
The staging script generates the exact names and refuses collisions. Target
archives are renamed externally without recompression. Editing their contents
requires rebuilding and requalifying during candidate preparation.

**Official Apizr distribution images remain deferred to subsequent deliveries.**
The CI worker image inventory is test evidence, not a public installation image.
No official image registry or completion claim is invented. This does not defer
the OCI plugin's already-qualified ability to build/publish user service images.
The [0.4.1/0.4.2 scope](../development/0.4.md#delivery-scope-and-explicit-deferrals)
remains unchanged.

## B. Authorized publication — do not execute during preparation

Only after phase A and explicit authorization, in the reviewed checkout:

```sh
test "$(git rev-parse HEAD)" = "$RELEASE_COMMIT"
(cd approved-assets && shasum -a 256 -c SHA256SUMS)
git tag v0.4.0 "$RELEASE_COMMIT"
git push origin refs/tags/v0.4.0
gh release create v0.4.0 --repo Alien6-Studio/outerspace-apizr --verify-tag --title 'Apizr 0.4.0' --notes-file docs/releases/0.4.0.md --draft
gh release upload v0.4.0 approved-assets/* --repo Alien6-Studio/outerspace-apizr
gh workflow run publish-pypi.yml --repo Alien6-Studio/outerspace-apizr --ref v0.4.0 -f ci_run_id="$REVIEWED_MASTER_RUN_ID"
```

Prepare the public release description from the reviewed notes with the actual
identities/status; the draft is not an announcement of availability. **Attaching
installation resources is an explicit maintainer action** above. The PyPI workflow
does not automatically attach every catalog/target export.

The existing workflow rechecks tag/commit, required runs, original distributions,
metadata and provenance; stages missing files; requests receipt approval; signs,
timestamps and verifies the delivery; then requests publication approval. Its
isolated publisher sends **core → OCI → MCP → Attest**. It subsequently downloads
and compares all eight public archives, then archives receipt/comparison evidence.
Wait for and inspect each result. A successful upload alone does not finish release.

If publication is partial, retain the same tag, run and bytes. Inspect which files
are public, then repeat the manual workflow with those same inputs. Existing files
must match both metadata SHA-256/size **and downloaded bytes**. A network/access
error is not absence. No `skip-existing`, replacement or automatic version bump.
An existing GitHub attachment must likewise be downloaded and compared; do not
use `--clobber` or recreate the release. Attach only missing identical resources.

## C. After verified publication

1. Verify the workflow's public comparison. In fresh environments outside the
   checkout, install `outerspace-apizr==0.4.0` from PyPI and run the candidate
   Quickstart's explicit operator policy and real REST/MCP calls. Download the
   draft release resources as maintainer, verify their provenance/hashes, install
   a profile through catalog → lock → sync, activate and run the analysis server.
   Compare public PyPI files with the eight approved originals. Once the assets
   and public installations pass, publish the GitHub release draft explicitly:

   ```sh
   gh release edit v0.4.0 --repo Alien6-Studio/outerspace-apizr --draft=false
   ```

   Confirm unauthenticated users can download the same release attachments.
2. Update the single current [Quickstart](../getting-started/quickstart.md) and
   [installation guide](../getting-started/install.md) to use verified public
   packages. Do not create a Quickstart per release. Preserve every existing
   anchor and keep the former candidate URL as a forwarding entry only.
   Historical scalar-response checks remain frozen test fixtures, outside the
   published documentation; current MCP examples assert object responses.
3. Update `install.md`, home, release notes, compatibility and navigation labels
   to the verified status and working public resource URLs. Search transitional
   text with `rg -n 'development.*0.4|0.4 development|not released|not published|Preparing 0.4' docs mkdocs.yml`.
   Review each occurrence: remove release-transition labels from current guides,
   preserve historical 0.3 facts, and keep 0.4.1/0.4.2 deferrals future-tense.
   Update `scripts/docs_build.py` status/stable release and its critical text,
   plus corresponding HTML/publication tests. Do not remove the build marker.
4. Record **release commit** and newer **documentation commit** separately. Run:

   ```sh
   uv run --locked --group docs mkdocs build --strict
   uv run --locked python scripts/check_docs_html.py
   ```

   Merge/deploy that documentation only after separate authorization. Let the
   existing Documentation workflow publish it; no direct gh-pages writes. It
   invokes `scripts/check_docs_site.py` against the exact site and deployment
   commit, compares `build-info.json` and critical HTTPS bytes, and must succeed.
   Keep logo, hero and video unchanged. Close publication tracking only after
   public package/plugin calls, resource downloads and deployed HTTPS content
   are verified. The documentation commit may be newer than the immutable
   release commit; it never reconstructs or replaces published packages.
