# Contributing to Apizr

Bug reports, focused fixes, tests and documentation improvements are welcome.
Search existing issues first. Include a minimal reproducer, Python/Apizr versions,
expected behavior and actual output. Discuss larger changes in an issue before
implementation. Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Developer Certificate of Origin

New contributions require the [Developer Certificate of Origin 1.1](https://developercertificate.org/).
By adding your own `Signed-off-by: Your Name <your-email>` trailer, you declare
that you have the right to submit the contribution under its open-source license
and accept the public contribution record described by the DCO. Read it before
signing. This declaration is separate from a cryptographic commit signature and
does not transfer copyright.

Use `git commit -s` with your own configured name/email. The required `quality`
check verifies that each new non-merge commit has a matching author sign-off.
An unsigned commit cannot pass merely because it belongs to a maintainer or bot.
Existing history is not rewritten; the initial 0.2.1 preparation commit predating
adoption has an explicit, immutable exception in the checker.

For an omission in your own unmerged commit, amend it with `git commit --amend -s`
and update your PR safely. Alternatively, a responsible submitter who can make
the DCO declaration for the referenced work may add a follow-up commit containing
their own sign-off and one `DCO-sign-off-for: FULL_COMMIT_SHA` trailer per earlier
commit in the audited range. This is an explicit declaration by that submitter, not a
fabricated signature of the original author. It also permits a maintainer to
review and take responsibility for automated dependency updates without changing
their original authorship. Bots receive no automatic exemption. A remediation
without the submitter's matching sign-off, or referring outside the checked range,
fails. CI retains the audit range after `83e28cb5d8ffbb4cb820122e125b03695e10fda8`
for branches based on that history. This includes the published #143 squash and
its subsequent corrective declaration in every audit, without rewriting history
or exempting the original commit. Branches predating that baseline retain their
event-specific range.

A squash merge creates a new commit. Its sign-off must match the **resulting
commit author's name and email**, which GitHub may choose from the account profile
rather than local Git configuration. Verify that identity before merging. Retain
a remediation trailer in the squash message when its target remains in the
audited history; omit references to replaced branch commits. Never amend or
force-push an already published commit to repair its declaration.

GitHub's default squash message is the pull request title and description, not
the branch commits: sign-offs carried only by the replaced commits do not reach
the published squash. Write the merge message explicitly (for example
`gh pr merge --squash --subject … --body …`) with the sign-off matching the
resulting author, as the #283 squash showed.

GitHub may retain the pull request author's identity for a Dependabot squash,
even when the merge request supplies the maintainer's author email. A maintainer
sign-off alone then does not match the resulting bot author. Check the published
commit identity as well as the proposed merge message; never add a bot's sign-off
on its behalf.

For a protected squash whose sign-off does not match its Git author, including
a retained bot author or a GitHub login used instead of the author's name,
leave that commit unchanged. Open a corrective PR from
the current protected branch. The new responsible declaration must match the
corrective commit's author and explicitly identify the original squash:

```text
Signed-off-by: Your Name <your-email>
DCO-sign-off-for: FULL_COMMIT_SHA
```

If that corrective PR is squash-merged, preserve both trailers and ensure the
resulting author is `Your Name <your-email>`, not the GitHub login.

## Development workflow

The current development line is the official `0.4.6` branch. Branch from it and
target it for product fixes. Stable `master`, immutable release
tags and published archives stay outside development changes. The maintainer
must validate the branch and complete its protected integration before separately
authorizing a release. A merge alone never publishes a package or site.
See [release governance](https://apizr.outerspace.sh/contributing/release-branches/).

Website sources and the Academy live on `gh-pages`, with their own locked
environment, checks and GitHub Pages deployment. Open website PRs against that
branch. Product examples, schemas, release records and executable qualification
fixtures stay on the product branches and retain product qualification.
See the [website workflow](https://github.com/Alien6-Studio/outerspace-apizr/blob/gh-pages/README.md).

```sh
git fetch origin
git switch -c feature/my-change origin/0.4.6
```

Fork the repository if needed. Install uv and run:

```bash
uv sync --locked --group docs
uv run pre-commit install
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing
uv build
uv run --group docs mkdocs build --strict
uv run pre-commit run --all-files
uv run python scripts/smoke_container.py --python-version 3.11
```

The Docker check requires Docker. See [development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/) for wheel
validation and the dependency audit. Python 3.11–3.14 remains supported. Use Python 3.11 or
newer for security tooling. Ruff formats repository code; Black is a runtime
notebook-formatting dependency and is not the repository formatter.

Keep changes scoped, add regression tests for changed behavior and update the
relevant documentation. Before submitting a PR, check:

- [ ] Changes to commands, prerequisites, contracts or limits update the affected
  documentation, or the PR explains why no documentation change is needed.

Preserve legacy golden fixtures; integrity hooks exclude
them from automatic rewriting. Do not execute untrusted generated applications.
Submit a pull request explaining the problem, behavior and validation; retain
historical issues unless their acceptance criteria are actually satisfied.

Contributions retain [GPL-3.0-or-later](LICENSE). Participation follows the
[Code of Conduct](CODE_OF_CONDUCT.md).


Dependency changes must follow the [source, vulnerability and license review policy](https://apizr.outerspace.sh/contributing/dependencies/).
Security-sensitive changes must pass `uv run --locked python scripts/security_mutations.py`;
it runs in a disposable copy and fails if a selected protection can be removed
without its designated test detecting the regression.
