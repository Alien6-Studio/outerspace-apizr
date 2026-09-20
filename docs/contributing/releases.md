# Publishing a release

This page is for maintainers publishing Apizr itself. To install or upgrade a
checkout, use [Start here](../getting-started/introduction.md) and the
[migration notes](../getting-started/developer-guide/releases.md).

## PyPI ownership

Deleting a PyPI organization does not necessarily delete the package or remove individually assigned project permissions. Verify the `outerspace-apizr` project and its individual **Owner** permissions in the PyPI account before attempting a release. Do not rename or recreate the package merely because an organization was deleted.

A personal PyPI account can maintain the project. Organization accounts are optional; community organizations are free subject to PyPI approval, while corporate accounts are paid. An open-source license alone does not determine the organization's classification.

References: [PyPI organization FAQ](https://docs.pypi.org/organization-accounts/org-acc-faq/), [organization accounts](https://docs.pypi.org/organization-accounts/).

## Release procedure

1. Confirm project ownership, available version number and the target index (TestPyPI or PyPI).
2. Run the [development quality gates](../getting-started/developer-guide/setup.md#quality-gates), including the documentation, installed-wheel and container checks.
3. Verify the wheel in a separate environment outside the checkout and review the release notes.
4. Configure a [Trusted Publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/) for the actual GitHub repository if automated publication is desired. No organization subscription is required.
5. Publish the reviewed artifacts only as a deliberate release action. This repository currently builds artifacts in CI and does not automatically publish to PyPI.

The 0.2.0 changes are not available through `pip install outerspace-apizr` until a release is actually published. Install from this checkout in the meantime.

## Documentation publication

Documentation is deployed independently of PyPI releases. On pull requests, the
Documentation workflow runs a strict MkDocs build. A push to `master`, including a
merged PR, runs the build and then publishes the generated site to `gh-pages`.
GitHub Pages serves that branch at [apizr.outerspace.sh](https://apizr.outerspace.sh/).
Edit Markdown under `docs/` and navigation in `mkdocs.yml`; `gh-pages` contains
build output and must be retained as the active publication branch.
