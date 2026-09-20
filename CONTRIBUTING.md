# Contributing to Apizr

Bug reports, focused fixes, tests and documentation improvements are welcome.
Search existing issues first. Include a minimal reproducer, Python/Apizr versions,
expected behavior and actual output. Discuss larger changes in an issue before
implementation. Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Development

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
uv run python scripts/smoke_container.py --python-version 3.8
```

The Docker check requires Docker. See the developer guide for wheel validation
and the dependency audit. Python 3.8–3.14 remains supported. Use Python 3.11 or
newer for security tooling. Ruff formats repository code; Black is a runtime
notebook-formatting dependency and is not the repository formatter.

Keep changes scoped, add regression tests for changed behavior and update the
relevant documentation. Preserve legacy golden fixtures; integrity hooks exclude
them from automatic rewriting. Do not execute untrusted generated applications.
Submit a pull request explaining the problem, behavior and validation; retain
historical issues unless their acceptance criteria are actually satisfied.

Contributions retain [GPL-3.0-or-later](LICENSE). Participation follows the
[Code of Conduct](CODE_OF_CONDUCT.md).
