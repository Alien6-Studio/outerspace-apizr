# Compatibility notes

<span id="migration-and-releases"></span>

## From 0.2.1 to the 0.3.0 candidate

Latest published stable: **0.2.1**. Repository candidate: **0.3.0**, not yet published.
Existing single-source and legacy commands remain available,
and no canonical contract meanings change. Repository Exposure is an explicit new
workflow; nothing is published or migrated automatically. See the
[0.3 notes](../../releases/0.3.0.md) for policy composition, execution boundaries and
known limitations. Use `[legacy]` to retain the combined notebook/legacy/web
dependency stack. The default 0.3 installation is minimal;
select `notebook`, `http`, `mcp` or `legacy` extras explicitly.

The following environment and legacy notes include changes already present in 0.2;
they are not additional breaking changes introduced by 0.3.

## Supported environments

- **Python 3.11–3.14 only**, for both Apizr and generated targets.
- Use a supported interpreter and deployment image. Set `--python-version` and YAML `python_version` targets; unsupported targets fail with the supported range. Existing source is parsed, never transpiled.
- Application APIs live under `apizr`; use Python standard-library APIs for interpreter compatibility.
- Security minima for FastAPI, Starlette, python-multipart, nbconvert, Black and pytest are documented in the [current security baseline](../../architecture/security-baseline.md). Pydantic 2 remains in use.
- One PEP 621 package definition and `uv.lock` describe the supported package and development environment.
- Imports work from an installed wheel, without changing `sys.path`.
- Non-interactive CLI defaults; `--force` remains accepted and `--interactive` enables prompts.
- The pipeline passes the converted script and generated API module through every stage.
- Function defaults, async functions, positional-only and keyword-only arguments are preserved. Dynamic argument lists are explicitly rejected.
- Type resolution uses the original module at API startup, including user-defined Pydantic models.
- Containers use Uvicorn directly, Debian slim by default, a non-root user and a health endpoint.
- Dependency inference no longer runs pipreqs or imports the analyzed modules. Explicit requirements are supported.
- HTTP generation returns a ZIP instead of writing to caller-selected paths. Directory scanning and the old `/dockerize_file/` endpoint are removed. The notebook endpoint returns script text. Docker endpoints return generated content.
- Non-empty output directories are rejected. Choose a new directory when regenerating.

## Adopt compiler workflows incrementally

The `--script` / `--notebook` legacy pipeline remains supported. Its discovery,
routes and configuration are independent of the Capability Compiler; existing
projects do not automatically switch to the new generators.

Use `apizr scan` and `apizr graph` to inventory a repository, `apizr inspect` for
Capability IR and static readiness, and `apizr readiness` for repository policy
evidence. Generate explicit REST/MCP interfaces with `apizr generate rest` or
`apizr generate mcp`. Governed local/OCI execution and governed transports are
opt-in and experimental; inspect their policies and operational prerequisites.
None of these static assessments grants trust or makes arbitrary Python safe.

Selected legacy duplicate definitions/overload sets and duplicate routes now fail
early ([#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28)); use an
unambiguous wrapper or exclude the conflicting definitions. Class/method
capabilities remain unsupported. The 0.3 candidate adds an opt-in
[strict OCI subprocess-deny profile](../../architecture/subprocess-deny.md). See the
[0.2.0 release notes](../../releases/0.2.0.md) for scope and boundaries.

## PyPI ownership

Maintainers: see [package ownership](../../contributing/releases.md#pypi-ownership).

## Release procedure

Maintainers: see [publishing a release](../../contributing/releases.md#release-procedure).
User installation and migration do not require PyPI ownership or publication.
