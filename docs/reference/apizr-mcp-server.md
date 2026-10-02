# Apizr as a local MCP server

For prerequisites and package availability, see [Install Apizr](../getting-started/install.md).

The optional **outerspace-apizr-mcp** plugin exposes local analysis and planning
through stdio. **Default mode remains read-only, with exactly three tools.**
The **0.4.2 version prepared for final publication** adds delivery only when the
operator supplies `--delivery-request` at startup. It does not generate bundles,
build images, execute business functions, acquire Git sources or install plugins. A **generated business MCP
server** exposes the capabilities you selected; this server exposes Apizr's
compiler operations. They are different applications.

## Install and activate explicitly

Follow [Install Apizr → choose a plugin profile](../getting-started/install.md#choose-a-plugin-profile)
with **`mcp`**. Use its verified exported wheels and locks; users do not need
to build plugins or compute dependency closures. Keep that workspace as `$work`,
with `core/` and the explicit `plugins/` store. For the MCP example below, create
the directories below, then save the four files shown in the next section.

```sh
export work="$PWD"
mkdir -p project/src project/policies
```

<details markdown="1">
<summary>Advanced: build and prepare wheels from a source checkout</summary>

Use macOS or Linux, Python 3.11–3.14 and uv. Build the core and plugin from the
**same recorded commit**. Preparation below can download build tools and locked
dependencies. Installation by Apizr uses only the reviewed local wheelhouse.
The SDK and a copy of the compiler belong to the plugin's separate environment;
the minimal core receives neither MCP nor REST dependencies.

For `0.4.2`, currently unpublished, use the source checkout:

```sh
work=$(mktemp -d)
work=$(cd "$work" && pwd -P)
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
  wheels/outerspace_apizr-0.4.2-py3-none-any.whl
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
plugin_sha=$(prepare/bin/python -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("wheels/outerspace_apizr_mcp-0.4.2-py3-none-any.whl").read_bytes()).hexdigest())')
core/bin/apizr plugins install wheels/outerspace_apizr_mcp-0.4.2-py3-none-any.whl \
  --sha256 "$plugin_sha" --requirements plugin.lock --wheelhouse wheels \
  --plugins-dir "$work/plugins"
core/bin/apizr plugins enable outerspace-apizr-mcp --version 0.4.2 --plugins-dir "$work/plugins"
```

Installation alone leaves the plugin inactive. The existing [locked installation
rules](local-extensions.md) apply. No installer runs at server
startup. A missing, inactive, inconsistent or missing-interpreter installation
is refused without repair.


</details>

## Choose one local project

Create `project/` with this complete `apizr.toml`:

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

From `$work`, prepare and review an explicit analysis grant:

```sh
core/bin/python - <<'PYTHON'
import json
from pathlib import Path
root = str(Path("project").resolve())
Path("operator.json").write_text(json.dumps({"schema":"apizr.operator-policy/v1","grants":[{"adapter":"repository","operation":"analyze","target":{"kind":"local","root":root},"permissions":["source.analyze"]}]}))
PYTHON
```

Start with absolute paths:

```sh
"$work/core/bin/apizr" mcp serve --project "$work/project/apizr.toml" \
  --operator-policy "$work/operator.json" \
  --plugins-dir "$work/plugins"
```

Without `--plugins-dir`, the existing `--user-config` selection or default plugin store applies. The resolved selection is captured once at startup. The core
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
The three analysis tool descriptions and read-only annotations are fixed; repository text remains
data and cannot create tools or replace server instructions. Annotations alone
are not an authorization boundary.

## Explicit delivery mode (0.4.2)

The default launch remains:

```sh
apizr mcp serve \
  --project /absolute/project/apizr.toml \
  --operator-policy /absolute/operator.json
```

It exposes only analysis, readiness and exposure planning, even when delivery
plugins and delivery grants already exist. To enable delivery, the operator
selects one existing [BatchRequest](multi-destination-delivery.md) containing a
qualified build and its explicit destinations:

```sh
apizr mcp serve \
  --project /absolute/project/apizr.toml \
  --operator-policy /absolute/operator.json \
  --delivery-request /absolute/delivery.json \
  --plugins-dir /absolute/plugins
```

The launcher reads the request once: an absolute regular file, at most 512 KiB,
with no symlink traversal or duplicate JSON keys. Existing strict `BatchRequest`
validation binds the shared build, proof requirement and ordered unique destinations.
A private inherited descriptor carries the frozen request, policy and plugin-store
selection. Restart to select different values; editing their files does not change
an active session. Delivery authority is not included in analysis worker jobs.

| Additional tool | Exact accepted arguments | Result and effects |
| --- | --- | --- |
| `apizr_delivery_status` | `{}` | Existing `BatchResult`, local evidence only; no directory creation, plugin invocation or network |
| `apizr_delivery_run` | Required `expected_delivery_manifest_digest` | Existing coordinator starts the captured request; retained evidence prevents a silent restart |
| `apizr_delivery_resume` | Required `expected_delivery_manifest_digest` | Existing coordinator resumes retained progress and verifies remote state; missing evidence is refused |

The confirmation is the existing digest object:

```json
{"expected_delivery_manifest_digest":{"algorithm":"sha256","value":"<64 lowercase hexadecimal characters>"}}
```

All three schemas forbid extra fields. Run/resume require the confirmation to
match the digest returned by status before any coordinator call. The client
cannot submit destinations, credentials, keys, plugin paths, evidence roots,
recovery selections, requests or authority. Each underlying managed operation
still requires its exact existing operator grant, plugin identity and repository.
MCP creates no permission or grant; annotations grant no authority.

Status returns the exact retained complete/partial result. Without evidence,
all destination outcomes are `not_started`; the existing aggregate schema uses
`state: failed` until a destination completes. This is a successful status call,
with `isError: false`, and creates no evidence. Run/resume likewise return typed
`complete`, `partial`, `failed` or `cancelled` business results with `isError: false`.
They reuse the 0.4.1 `deliver_batch` coordinator and do not rebuild, regenerate,
resolve dependencies or blindly re-sign completed destinations.

Status is annotated read-only, idempotent and closed-world. Run/resume are
annotated effectful, non-idempotent and open-world; all three use
`destructiveHint: false` because they do not delete remote state. Run/resume may
write local evidence and remote images, proofs and destination tags. No automatic
retries or rollback are added. Cancellation preserves confirmed progress and
uncertainty for in-flight mutations, stops later destinations and waits for native
cleanup. Unconfirmed cleanup produces `cleanup_unconfirmed` and ends the session.

Fixed refusals include `delivery_not_enabled`, `delivery_identity_changed`,
`delivery_evidence_invalid`, `delivery_operation_failed`, `cleanup_unconfirmed`,
`invalid_arguments`, `arguments_too_large`, `response_too_large` and `server_busy`.
When delivery is not enabled its tools are absent and receive the normal
unknown-tool refusal. No raw exception, operational path or secret is returned.

## Bounds and lifecycle

Startup-only options:

| Option | Default | Accepted range |
| --- | --- | --- |
| `--timeout-ms` | 10,000 per call | 1–600,000 |
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

One call runs at a time across analysis and delivery tools. Overlapping calls get `server_busy`; discovery
remains responsive. Timeout affects a calculation, not the connection lifetime.
MCP cancellation, EOF, client disconnection and SIGINT/SIGTERM/SIGHUP cancel active
work through the existing runtime and wait for pipe closure and child recovery.
Unconfirmed cleanup ends the session with an explicit diagnostic. Ordinary
process-group descendants are covered by the runtime; detached descendants
remain outside its documented cleanup guarantees. No plugin or project code is
imported by the core, and project code is not executed by analysis.

There is no automatic `.env` load, inherited secret environment, HTTP/SSE server,
OAuth, sampling, LLM call, telemetry or Git acquisition. Only explicitly enabled
delivery can perform the selected registry and proof operations. Results
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
        "--operator-policy", "/absolute/work/operator.json",
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
not tests of a graphical client. See the [release record](../releases/0.4.1.md)
for publication status.

Delivery qualification adds official SDK status/run/resume calls for both protocol
revisions. `scripts/smoke_oci_registry.py --artifacts --output /absolute/new-proof`
reuses the disposable authenticated HTTPS registry, TSA, Attest, ORAS and Docker
fixture. It exercises complete delivery and A/C complete with B failed followed by
B recovery, checks retained digests, upload/signature counts and zero new builds,
and runs delivered REST/MCP services after original source and bundle removal.
The installed lifecycle proof covers cancellation, EOF, disconnection and signals
with a synchronized native worker and retained batch evidence.

## Qualification evidence

The `MCP server plugin` workflow has two independent jobs, with no dependency
between them:

- `stdio`: the installed analysis plugin and official SDK client, including
  separate plugin coverage and the Linux proof without network access, on Linux
  Python 3.11–3.14 and macOS 3.11/3.14;
- `generated-recovery`: ten predetermined repetitions **per transport** of the
  generated business MCP server recovery test, on Linux/macOS Python 3.11.

An error in either job does not prevent the other from running. Both jobs and
the general CI must succeed on the same final commit to complete qualification.
A prior green run, skipped job or successful later call is not a replacement for
that evidence. Artifacts are retained on failure; repetitions are never retried
until green.

Run the recovery series with a fresh output directory:

```sh
uv run --locked python scripts/repeat_mcp_transports.py --output /tmp/mcp-recovery
```

Each JUnit report contains redacted call history and bounded `execution_phases`:
process launch, worker bootstrap/import completion, request reception/validation,
source binding, calculation, response and cleanup. Every completed exchange must
show a reaped direct child and closed stdin/stdout; the test also checks that the
recorded worker PIDs no longer exist. Records contain interpreter path, version,
architecture, timestamps and process/pipe state, never arguments or business
results. The test-only observer wraps the embedded runtime without changing the
generated artifacts, public protocol or production defaults. Its overhead is
included in timings; local and runner interpreter identities must be compared
explicitly before drawing conclusions.

The functional recovery test uses a fixed 5,000 ms policy (the existing execution
policy default), measured **before process creation**, including interpreter
startup/imports and waiting for process exit. Infinite loops and blocked calls
still produce real timeouts; crashes, output overflow, artifact tampering and
subsequent successful calls remain asserted. Dedicated tests in
`tests/execution/test_deadline.py` retain real 100 ms deadlines, prove that a
budget consumed inside `Popen` is not restarted, and check reaping and closed
pipes before recovery.

The former 1,000 ms functional budget conflated recovery with cold-process
performance. In the initial measured macOS 3.11.9 series, an expected `fail`
exchange took 974.489 ms although calculation took 0.143 ms: imports took
344.340 ms, the response was available around 521 ms, and cleanup began around
951 ms. Linux 3.11.15's slowest non-timeout exchange took 183.896 ms; local
macOS 3.11.14 measured 225.503 ms. These are different interpreters/environments,
not interchangeable benchmarks. The existing 5-second default gives the
functional checks margin above this measured near-boundary exchange, while the
separate short-deadline tests retain the timing contract. Production defaults
and the start of deadline measurement are unchanged.

[Issue #142](https://github.com/Alien6-Studio/outerspace-apizr/issues/142) retains
all historical failures and per-commit qualification links. The old logs did not
measure internal phases: their exact startup/shutdown split cannot be recovered.
No specific OS scheduling or interpreter defect is claimed from those logs.

## Session authority

The launcher checks source admission before server execution, preserving active
installation checks and the usage lease. It hands the captured policy and project
scope through a bounded private inherited descriptor, not a policy path to reopen.
Workers recheck the shared gate, and the server checks before spawning a worker.
Device/inode pinning refuses root replacement; descriptor traversal prevents a
pathname change redirecting analysis. Only explicitly chosen bounded configuration
is read before admission. Policy/project edits require a restart: no dynamic
revocation is promised. Clients cannot supply new roots, grants or operator paths.
Exposure proposals remain selection policies, never source authority. Default
tools remain local stdio analysis/readiness/planning. Explicit delivery uses a
separate captured session section; no Git acquisition, generation or build tool
is exposed.
