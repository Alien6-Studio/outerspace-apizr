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
commit in the PR. This is an explicit declaration by that submitter, not a
fabricated signature of the original author. It also permits a maintainer to
review and take responsibility for automated dependency updates without changing
their original authorship. Bots receive no automatic exemption. A remediation
without the submitter's matching sign-off, or referring outside the checked range,
fails. A squash merge creates a new commit: give it the responsible submitter's
own sign-off; retain earlier declarations in the PR history, without copying
range-specific remediation references into the new squash commit.

## Development workflow

Fork the repository and create a focused branch. Install uv and run:

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

The Docker check requires Docker. See [development and checks](docs/getting-started/developer-guide/setup.md) for wheel
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


Dependency changes must follow the [source, vulnerability and license review policy](docs/contributing/dependencies.md).
Security-sensitive changes must pass `uv run --locked python scripts/security_mutations.py`;
it runs in a disposable copy and fails if a selected protection can be removed
without its designated test detecting the regression.
