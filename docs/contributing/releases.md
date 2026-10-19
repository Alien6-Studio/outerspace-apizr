# Publishing a release

This guide is for maintainers preparing Apizr 0.4.6. To propose a code change,
start with [Contributing](../about/CONTRIBUTING.md). Published versions and their
changes are listed in the [GitHub releases](https://github.com/Alien6-Studio/outerspace-apizr/releases).

## 1. Prepare the version

Update the core and all three plugins together. Check their versions, internal
dependency pins, package READMEs and the notes in `releases/0.4.6.md`. The
project URLs should link to the repository, documentation, issues and releases.
There is no separate changelog to maintain.

Also review the CLI Action defaults, plugin descriptors, MCP launcher metadata,
Docker source reference and pinned VS Code source. Run:

```sh
uv run --locked python -m scripts.qualification.packaging.check_release_metadata --release
```

The check binds these files to the candidate build. If a README or package
setting changes afterward, build and qualify a new candidate.

## 2. Qualify the candidate

Follow [release branch governance](release-branches.md) for the branch to qualify
and integrate. Wait for all required CI and security checks on the exact commit.
Do not use an older successful run as proof for newer code.

Review the wheels, source archives, checksums and installation results for every
supported target. The [verification guide](verification.md) explains how to
download and check them. The [VS Code procedure](vscode-distribution.md) covers
the separately built extension.

Keep the original CI artifacts for publication. Do not rebuild them on a laptop
for upload. Preparing a candidate or merging a product PR does not publish it.

## 3. Review the final release

Before creating the tag, check that:

- The release notes describe the code and explain breaking changes.
- Installation commands, the installation GIF and examples use the target version.
- The four package descriptions render correctly and match the built archives.
- Required tests, coverage, dependency audits and security checks pass.
- Open release blockers are resolved.

Create the protected `v<version>` tag on the approved integration commit. Use the
reviewed notes for the GitHub release and attach the original CI artifacts.

## 4. Publish and verify

Publication is a separate maintainer action using the protected workflows and
their reviewed CI run. Follow [package publication](publish-0.4.md) and
[release verification](verification.md). PyPI uses its configured Trusted
Publisher; tags and published archives must remain unchanged.

After publication, install the package in a clean environment. Check its version,
run an example and compare the public file hashes with the approved artifacts.
Check that versioned source links and release-asset URLs resolve to the published
tag and original archives. Record the publication results in the release notes.
Homebrew, MCP registries and extension registries have their own publication steps.

If publication only partly succeeds, inspect the public state before retrying.
Reuse the approved files; do not replace an existing release with a rebuilt one.

## Documentation publication

The website lives on `gh-pages`. Open website PRs against that branch and use the
[website README](https://github.com/Alien6-Studio/outerspace-apizr/blob/gh-pages/README.md)
to preview and check the change.

`site.json` identifies the documented product revision and whether it is a
development or stable version. `downloads.json` identifies the source of the
downloadable examples. Update them when the corresponding product revision has
been reviewed. A website update does not publish a Python package.

### Build once and verify publication

After a merge, the workflow checks the site and deploys the built Pages artifact.
It then verifies the public HTTPS files against `build-info.json`. That file,
linked in the footer, identifies the deployed source and file hashes. A stale or
mixed deployment fails verification.

## Repository protections

Use normal PRs and keep required checks, signed commits, DCO sign-offs and
resolved review threads. Do not bypass protection or rewrite published tags.
The publication environment requires its own maintainer review. See
[release governance](release-branches.md) for the current settings.

## Website previews and privacy

When changing the website layout, check the homepage and a nested page on both
desktop and mobile. Confirm social-link previews use the expected title and
image. Test cookie rejection and optional GitHub statistics separately; the
website does not use Google Analytics.

For historical publication results, use the version's release notes rather than
replaying a procedure written for an older version.

<span id="046-preparation-and-publication-boundary"></span>
<span id="additional-evidence-for-future-releases"></span>
<span id="authorized-045-finalization"></span>
<span id="automatic-development-qualification"></span>
<span id="completed-043-qualification"></span>
<span id="completed-044-finalization"></span>
<span id="current-published-baseline"></span>
<span id="dated-directory-verification-after-authorized-publication"></span>
<span id="development-iteration-and-pr-qualification"></span>
<span id="finalizing-044"></span>
<span id="historical-044-published-baseline"></span>
<span id="mcp-distribution-045"></span>
<span id="ownership-and-one-time-setup"></span>
<span id="parallel-full-suite-qualification"></span>
<span id="published-030"></span>
<span id="published-releases-and-verification-builds"></span>
<span id="pypi-ownership"></span>
<span id="release-checklist"></span>
<span id="release-procedure"></span>
<span id="retain-and-publish-one-coordinated-artifact-set"></span>
<span id="site-analytics-review"></span>
<span id="social-link-previews"></span>
<span id="vs-code-distribution-preparation-for-046"></span>
<span id="web-only-changes"></span>
