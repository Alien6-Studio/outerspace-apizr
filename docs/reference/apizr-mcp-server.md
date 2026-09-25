# Apizr as a local MCP server

!!! warning "0.4 development — not released"

    This feature requires wheels built from this development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel)
    and record the source commit. This page ships with the feature PR; it does
    not describe a released plugin. The public site's build marker identifies
    which documentation revision has actually been deployed.

The optional **apizr-mcp** plugin exposes read-only local analysis and planning
through stdio. It does not generate bundles, execute business functions, acquire
Git sources, install plugins or publish artifacts. A **generated business MCP
server** exposes the capabilities you selected; this server exposes Apizr's
compiler operations. They are different applications.

## Install and activate explicitly

Use macOS or Linux, Python 3.11–3.14 and uv. Build the core and plugin from the
**same recorded commit**. Preparation below can download build tools and locked
dependencies. Installation by Apizr uses only the reviewed local wheelhouse.
The SDK and a copy of the compiler belong to the plugin's separate environment;
the minimal core receives neither MCP nor REST dependencies.

From the source checkout:

```sh
work=$(mktemp -d)
git rev-parse HEAD > "$work/source-commit.txt"
uv build --wheel --out-dir "$work/wheels"
uv build --wheel plugins/mcp --out-dir "$work/wheels"
uv export --locked --no-dev --extra mcp --no-emit-project \
  --output-file "$work/dependencies.txt"
cp -R examples/project-config "$work/project"
cd "$work"
uv venv --seed --no-python-downloads --python python3 prepare
prepare/bin/python -m pip download --only-binary=:all: --dest wheels \
  -r dependencies.txt
uv venv --no-python-downloads --python python3 core
uv pip install --python core/bin/python --offline --no-index --find-links wheels \
  wheels/outerspace_apizr-0.3.0-py3-none-any.whl
```

Record one exact version and SHA-256 per distribution, including the plugin,
core and all transitive dependencies. The export uses the repository's reviewed
lock; the final lock describes the actual wheels for this Python/platform.
Hashes establish integrity, not trust in their authors.

```sh
prepare/bin/python - <<'PY'
import hashlib
import zipfile
from email.parser import BytesParser
from pathlib import Path

lines = []
for wheel in sorted(Path("wheels").glob("*.whl")):
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(name))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    lines.append(f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{digest}\n")
Path("plugin.lock").write_text("".join(lines))
PY
plugin_sha=$(prepare/bin/python -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("wheels/apizr_mcp-0.0.0-py3-none-any.whl").read_bytes()).hexdigest())')
core/bin/apizr plugins install wheels/apizr_mcp-0.0.0-py3-none-any.whl \
  --sha256 "$plugin_sha" --requirements plugin.lock --wheelhouse wheels \
  --plugins-dir "$work/plugins"
core/bin/apizr plugins enable apizr-mcp --version 0.0.0 --plugins-dir "$work/plugins"
```

Installation alone leaves the plugin inactive. The existing [locked installation
rules](local-extensions.md) apply. The plugin's development version remains
`0.0.0`; this is not a package published on PyPI. No installer runs at server
startup. A missing, inactive, inconsistent or missing-interpreter installation
is refused without repair.

## Choose one local project

The copied `project/` contains this complete `apizr.toml`:

```toml
schema_version = "apizr.project/v1"
root = "."
readiness_policy = "policies/readiness.json"
exposure_policy = "policies/exposure.json"

[scan]
source_roots = ["src"]
excluded_directories = ["ignored"]
max_file_bytes = 4096

[graph]
max_ast_nodes = 10000
```

`src/calculator.py`:

```python
def add(a: int, b: int = 1) -> int:
    return a + b
```

`policies/readiness.json`:

```json
{"execution": {"modes": ["direct"]}}
```

`policies/exposure.json`:

```json
{
  "selection": {"include": ["python:calculator:add"]},
  "interfaces": ["rest", "mcp"],
  "execution": {"allowed": ["direct"]}
}
```

Paths resolve relative to `apizr.toml`, not the client's working directory. The
server freezes configuration and policy values at startup. Restart explicitly
to apply operator edits. Policy files must be regular files, at most 64 KiB,
without duplicate JSON keys. The existing project loader bounds TOML input.
The selected root is anchored by filesystem identity; symlink traversal and
root replacement cannot redirect a calculation to another project. Existing
scanner refusals and diagnostics remain visible.

Start with absolute paths:

```sh
"$work/core/bin/apizr" mcp serve --project "$work/project/apizr.toml" \
  --plugins-dir "$work/plugins"
```

Without `--plugins-dir`, the existing default plugin store applies. The core
validates the active installation and replaces itself with that environment's
interpreter and the registered `apizr_mcp` module. It passes an empty environment,
uses isolated Python, and reserves stdout for MCP. Diagnostics use stderr.

This durable connection is **not** `apizr plugins run`: that command retains its
one-request `apizr.extension/v1` protocol and existing timeout. Internally, the
MCP server uses that runtime for fresh, isolated **compiler calculations**, not
as an envelope around MCP traffic. Those workers call Python APIs, not the CLI.

## Tools and results

| Tool | Arguments | Structured result |
| --- | --- | --- |
| `apizr_analyze` | Optional `expected_repository_digest` | Existing canonical `catalog`, `graph`, and `repository_digest`; no retained raw sources |
| `apizr_readiness` | Optional `expected_repository_digest` | Existing canonical `report`, `repository_digest`, and the report's `exit_code` |
| `apizr_plan_exposure` | Optional `policy` (existing `ExposurePolicy`) and `expected_repository_digest` | Existing canonical `ExposurePlan`, including `repository_digest` |

For example, call `apizr_analyze` with `{}`, retain
`result.structured_content["repository_digest"]["value"]`, then call
`apizr_readiness` with `{"expected_repository_digest": "<that 64-digit digest>"}`.
Call `apizr_plan_exposure` with `{}` to use the startup exposure policy, or
`{"policy": {"selection": {"include": ["python:calculator:add"]},
"interfaces": ["mcp"], "execution": {"allowed": ["direct"]}}}` to propose a
plan. The proposal never overwrites files or authorizes execution.

A missing exposure policy yields `policy_required`; it never selects everything.
A changed digest yields `repository_changed`. Each call scans once; separate
calls can see changed source files. Readiness `exit_code: 1` is a valid business
report with `isError: false`, preserving unknown/conditional/refused distinctions.

Errors have `isError: true` and structured `error.code`/`error.diagnostics`:
`invalid_arguments`, `exposure_refused` (canonical planning diagnostics),
`scope_changed`, `repository_changed`, and redacted runtime/operational codes.
No internal traceback or raw subprocess diagnostic is returned. Strict tool
schemas reject client-supplied roots, policy paths, executables or startup limits.
Tool descriptions and read-only annotations are fixed; repository text remains
data and cannot create tools or replace server instructions. Annotations alone
are not an authorization boundary.

## Bounds and lifecycle

Startup-only options:

| Option | Default | Accepted range |
| --- | --- | --- |
| `--timeout-ms` | 10,000 per calculation | 1–600,000 |
| `--max-request-bytes` | 65,536 per stdio line | 4,096–1,048,576 |
| `--max-response-bytes` | 4,194,304 | 2,048–16,777,216 |

The argument allowance reserves 2 KiB within the request bound. Worker stdout
(including its private response envelope) is bounded while reading; an overflow
returns `size_limit`, never a truncated canonical report. Result serialization
is also checked (`response_too_large`). The SDK's protocol envelope and schemas
have a separate 256 KiB allowance. An oversized/invalid byte stream closes the
connection with a redacted stderr diagnostic such as `request_too_large`.
Protocol writes have a five-second deadline. Scanner limits still apply; these
bounds are not an operating-system memory quota or a sandbox.

One calculation runs at a time. Overlapping calls get `server_busy`; discovery
remains responsive. Timeout affects a calculation, not the connection lifetime.
MCP cancellation, EOF, client disconnection and SIGINT/SIGTERM/SIGHUP cancel active
work through the existing runtime and wait for pipe closure and child recovery.
Unconfirmed cleanup ends the session with an explicit diagnostic. Ordinary
process-group descendants are covered by the runtime; detached descendants
remain outside its documented cleanup guarantees. No plugin or project code is
imported by the core, and project code is not executed by analysis.

There is no automatic `.env` load, inherited secret environment, HTTP/SSE server,
OAuth, sampling, LLM call, telemetry, network acquisition or publication. Results
may contain project names, docstrings and diagnostics: **the MCP client may send
them to its model**. Local stdio alone does not guarantee confidentiality.

## Client configuration and validation

The real integration proof uses the official Python MCP SDK **2.2.0**, its
[current low-level API](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/advanced/low-level-server.md),
and a real SDK stdio client. It validates revisions **2026-07-28** (`auto`) and
**2025-11-25** (`legacy`). No JSON-RPC server implementation is duplicated here.

This VS Code `.vscode/mcp.json` example follows the official
[MCP configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).
Replace all paths; **the graphical VS Code connection has not been tested**.
No personal client configuration is changed by installation or this proof.

```json
{
  "servers": {
    "apizr": {
      "type": "stdio",
      "command": "/absolute/work/core/bin/apizr",
      "args": [
        "mcp", "serve", "--project", "/absolute/work/project/apizr.toml",
        "--plugins-dir", "/absolute/work/plugins"
      ]
    }
  }
}
```

From the checkout, `uv run --locked python scripts/smoke_mcp_server.py --output
/absolute/new-proof-directory` builds and installs separate wheels outside the
checkout, checks inactive refusal and explicit activation, compares all tools
against Python/CLI, and exercises actual subprocess cancellation/shutdown with a
synchronized test worker. It checks core files, activations and project contents.
The dedicated CI matrix covers Linux 3.11–3.14 and macOS 3.11/3.14 and preserves
logs and separate plugin coverage. Linux repeats the installed proof with network
access removed by a disposable network namespace. These are development proofs,
not tests of a graphical client or a claim that 0.4 has been published.
