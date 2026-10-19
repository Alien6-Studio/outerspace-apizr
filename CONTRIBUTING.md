# Contributing to Apizr

Bug fixes, tests and documentation improvements are welcome. For a larger change,
open an issue first so we can agree on the approach before you spend time on it.
Report security issues privately using [SECURITY.md](SECURITY.md).

<span id="development-workflow"></span>

## Set up your fork

You need Git, [uv](https://docs.astral.sh/uv/getting-started/installation/) and
Python 3.11–3.15 on macOS or Linux.

1. Fork the repository on GitHub.
2. Clone your fork and create a branch from the current development line:

```sh
git clone https://github.com/YOUR-USERNAME/outerspace-apizr.git
cd outerspace-apizr
git remote add upstream https://github.com/Alien6-Studio/outerspace-apizr.git
git fetch upstream
git switch -c fix/my-change upstream/0.4.6
uv sync --locked --group readme
uv run pre-commit install
```

Use your GitHub username in the clone URL and choose a branch name for your change.

## Make and check your change

Keep a PR focused on one change. Add a regression test for a bug fix and update
the relevant guide when behavior changes.

Run the tests for the code you changed, then the shared checks:

```sh
uv run pytest tests/path/to/test_file.py
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pre-commit run --all-files
```

Replace the test path with the relevant file. CI runs the full suite on your PR.
For the full local suite, first fetch the pinned VS Code source used by the
integration tests:

```sh
uv run --locked python -m scripts.qualification.packaging.vscode_source --prepare
uv run pytest
```

See [developer setup](https://apizr.outerspace.sh/getting-started/developer-guide/setup/)
for Docker checks and optional integrations.

<span id="developer-certificate-of-origin"></span>

## Open your pull request

Sign off your own commits with `git commit -s`. This confirms the
[Developer Certificate of Origin](https://developercertificate.org/): read it
before contributing. Configure your Git name and email first; each sign-off
must match the commit author. Protected branches also require a
[verified commit signature](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits);
configure signing before committing with `-S`.

```sh
git add path/to/changed-file.py
git commit -S -s -m "Fix the behavior described in the issue"
git push -u origin fix/my-change
```

Open a PR from your fork to **Alien6-Studio/outerspace-apizr**, with **`0.4.6`
as the base branch**. Describe the problem, what changes for users and how you
tested it. Link the related issue if there is one. Draft PRs are welcome when
you would like early feedback.

Check the CI results and respond to review comments. If a check fails, open its
log for the failing command. Ask in the PR when you need help reproducing it.

## Contribute to the website

The website and Academy use the **`gh-pages`** branch. For a website PR, start
your branch from `upstream/gh-pages`, follow its
[README](https://github.com/Alien6-Studio/outerspace-apizr/blob/gh-pages/README.md)
and choose `gh-pages` as the PR base.
