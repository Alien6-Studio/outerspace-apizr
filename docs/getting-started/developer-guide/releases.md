# Compatibility notes

<span id="migration-and-releases"></span>

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

The legacy duplicate-definition/overload limitation remains open as
[#28](https://github.com/Alien6-Studio/outerspace-apizr/issues/28). Class/method
capabilities and absolute subprocess prohibition remain unsupported. See the
[0.2.0 release notes](../../releases/0.2.0.md) for scope and boundaries.

## PyPI ownership

Maintainers: see [package ownership](../../contributing/releases.md#pypi-ownership).

## Release procedure

Maintainers: see [publishing a release](../../contributing/releases.md#release-procedure).
User installation and migration do not require PyPI ownership or publication.
