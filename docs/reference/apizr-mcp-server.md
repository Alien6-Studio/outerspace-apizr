---
title: Apizr MCP server for Python project analysis
description: Explore Python projects from your AI assistant with Apizr's MCP plugin. Inspect code, check readiness and choose the functions to expose.
---

# Apizr as a local MCP server

For prerequisites and package availability, see [Install Apizr](../getting-started/install.md).

Let your AI assistant explore a Python project with the optional
**outerspace-apizr-mcp** plugin. It can inspect code, check which functions are
ready to expose, and prepare a plan. By default, it is read-only and does not
execute your project's functions.

Find the plugin on [Glama](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr)
or the [official MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.Alien6-Studio%2Fouterspace-apizr).
To make your own functions callable by an assistant, use the
[MCP generation guide](../getting-started/user-guide/mcp.md).

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

For a temporary isolated profile, use the [verified preparation workflow](plugin-preparation.md).
It selects compatible wheels and normalizes multi-hash resolver locks without a
Python normalization script. Preparation installs nothing; installation and
activation remain explicit. Contributors use the same workflow with a local
wheelhouse containing core and plugin wheels from the same recorded commit.


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

<span id="directory-integration-043"></span>

## Use the directory launcher {#directory-integration-044}

The [official MCP Registry](https://registry.modelcontextprotocol.io/?q=io.github.Alien6-Studio%2Fouterspace-apizr)
lists Apizr as `io.github.Alien6-Studio/outerspace-apizr`.
[Glama](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr) also lists its
three analysis tools and their inputs.

After [installing and activating the MCP profile](../getting-started/install.md#choose-a-plugin-profile),
you can start it with:

```sh
uvx outerspace-apizr-mcp@0.4.4 \
  --project /absolute/project/apizr.toml \
  --operator-policy /absolute/operator.json \
  --plugins-dir /absolute/plugins
```

Replace the three paths with your project, permissions file and plugin directory.
This starts a local server; it does not install or activate the managed plugin.
For version 0.4.2, use `apizr mcp serve` instead.

Contributors can find publication checks in the
[release record](../contributing/verification.md#044-publication-record).

## Choose a tool: discover → assess → propose

The server's initialization instructions and tool descriptions explain this
journey directly to a connected assistant:

| Need | Choose | Next step |
| --- | --- | --- |
| Find what the project contains and obtain exact capability IDs | `apizr_analyze` for static source and relationship evidence | Review a capability and retain its repository digest if subsequent calls should use the same evidence |
| Understand whether a capability is usable and under which conditions | `apizr_readiness` for limitations, uncertainty and execution/control compatibility under the startup readiness policy | Inspect the relevant full, summary or exact detail result before choosing proposal constraints |
| Test a selection you already intend to expose | `apizr_plan_exposure` with an explicit policy or the captured startup exposure policy | Review the proposed capability/interface/execution combinations or the refusal diagnostics |

This is guidance, not a required sequence. Readiness and planning can be called
independently, including as the first call. Each tool assesses current evidence
within the startup source scope; earlier reports are not cached or supplied to
later calculations. Digest pinning checks consistency between independent calls.

These three tools do not execute project code, generate a server, change project
configuration or publish anything. A readiness report assesses evidence; a plan
is a proposal. Neither grants operator authority. Repository/root, operator
permissions and server bounds are chosen at startup. Tool arguments cannot
expand source scope, activate plugins, select infrastructure or enable delivery.

When delivery is explicitly enabled, initialization instead identifies the
additional effects: status inspects local evidence, while run/resume may mutate
remote state using captured authority. Analysis/readiness/planning remain
non-mutating in that mode. See [Explicit delivery mode](#explicit-delivery-mode-042).

## Tools and results

| Tool | Arguments | Structured result |
| --- | --- | --- |
| `apizr_analyze` | Optional `view`, exact detail filter, pagination and `expected_repository_digest` | Default/full: existing canonical `catalog`, `graph`, and `repository_digest`. Summary/detail: explicitly identified evidence view |
| `apizr_readiness` | Same view arguments | Default/full: existing canonical `report`, `repository_digest`, and `exit_code`. Summary/detail: states and focused evidence |
| `apizr_plan_exposure` | Optional `policy` (existing `ExposurePolicy`), `expected_repository_digest`, `offset` and `limit` | Existing canonical `ExposurePlan`; optional pagination applies only to refused-plan diagnostics |

The advertised JSON Schemas contain fixed descriptions and valid request examples,
including documentation under reusable `$defs`/`$ref` references. These are
generated from the canonical Pydantic models, independently of project text.

`expected_repository_digest` is an optional **plain string**: exactly 64 lowercase
hexadecimal SHA-256 characters, without a prefix or algorithm name. Omission or
`null` means normal discovery without asserting a previous identity. It does not
select a repository or change the startup source scope. Obtain the actual value
from a preceding response, rather than copying the illustrative digest in a
schema example. With an initialized official SDK client:

```python
analysis = await client.call_tool("apizr_analyze", {})
digest = analysis.structured_content["repository_digest"]["value"]
readiness = await client.call_tool(
    "apizr_readiness", {"expected_repository_digest": digest}
)
```

The response's reusable `Digest` object is
`{"algorithm": "sha256", "value": "<64 lowercase hexadecimal characters>"}`.
Its `algorithm` is fixed to SHA-256; only its `value` goes in the input pin.
Bounded views provide that same value at `identity.repository_digest.value`.
Pinning compares evidence discovered by the current call with the expected
identity; it neither caches the old repository nor disables discovery.

For `apizr_plan_exposure`, an explicit `policy` supplies the proposal constraints.
Omission or `null` uses the captured startup exposure policy; if neither exists,
the result is `policy_required`. For a discovered capability with compatible
startup readiness requirements, an explicit proposal has this shape:

```json
{
  "policy": {
    "selection": {"include": ["python:calculator:add"]},
    "interfaces": ["mcp"],
    "execution": {"allowed": ["direct"]}
  }
}
```

Use the exact ID returned by analysis. `selection.include_all_ready` adds the
report's READY capabilities to explicit `include`; `exclude` then removes exact
IDs. Unknown IDs are refused. `eligibility.allow_conditional` permits proposals
with CONDITIONAL required evidence, subject to all other checks; it does not
turn them into READY capabilities. `interfaces` requests `rest` and/or `mcp`.
`execution.allowed` is a nonempty acceptable mode set, with no ranking, default
or fallback; `execution.require` names required controls. Compatibility is also
constrained by the startup readiness policy.

**ExposurePolicy is a planning constraint, not operator authorization.** It
cannot enlarge the captured startup permissions. A successful `ExposurePlan`
contains selected capabilities, interfaces, compatible execution modes, static
readiness/relationship evidence and artifact/policy digests. It is a proposal,
not generation, execution, publication or an authority grant.

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

## Recover from a refusal

The same recovery guidance is available through initialization metadata.
Inspect `isError` and structured evidence, not just display text:

| Result | Existing recovery |
| --- | --- |
| `repository_changed` | Analyze current source evidence again, review what changed and its new identity, then decide whether to continue with the new digest. Never replace a pin blindly. |
| `policy_required` | Supply an explicit valid ExposurePolicy when no startup exposure policy was captured. This does not edit configuration or confer authority. |
| `exposure_refused` | Inspect `error.diagnostics` and supported `action` values; correct the proposal or evidence before another attempt. A refusal is not a successful plan. |
| Scope or authorization refusal | Operator/startup action is required. Alternative tool arguments cannot bypass captured scope or grants. |
| `server_busy` | The call was refused while another calculation was active. Wait for that call to finish before retrying an analysis tool. This is not a successful assessment or an automatic delivery retry. |
| `response_too_large` | For analysis/readiness, request summary, exact detail or smaller detail pages. For refused planning diagnostics, use their existing `offset`/`limit` pagination. Successful plans are not paginated; large individual records can still exceed the bound. No response is automatically truncated. |
| `arguments_too_large` / `invalid_arguments` | Correct or reduce the request within its advertised schema and startup bounds. These tools cannot raise server limits. |
| Transport, runtime, cleanup or operation failure | Preserve the failure and seek operator diagnosis where necessary. It is not a successful business assessment. Unconfirmed cleanup terminates the session. |

Tool refusals use `isError: true`; transport failures can instead prevent a tool
response. In contrast, readiness `exit_code: 1` with `isError: false` is a valid
assessment of limitations or uncertainty. Delivery business outcomes retain
their separate [existing semantics](#explicit-delivery-mode-042).

## Start with a small view (0.4.5 development)

Ask your AI assistant to summarize the repository before inspecting a function:

```json
{"view":"summary"}
```

Use this with `apizr_analyze` for source, capability and graph counts, or with
`apizr_readiness` for READY/CONDITIONAL/AMBIGUOUS/UNSUPPORTED counts, execution
compatibility and principal blockers. `principal_blockers` reports `total`, at
most ten `shown` diagnostics, and `has_more`; the sample is never presented as
all the evidence. Neither summary embeds a Catalog, Graph or Readiness report.

Then ask “Can I expose `python:model:predict`?” using `apizr_readiness`:

```json
{"view":"detail","capability_id":"python:model:predict"}
```

`focus` retains the exact identity, source path, local readiness, repository and
selected-scope states, interface eligibility and reasons. `principal_blockers`
remain visible on every page. `records` contains the required dependency context,
relationships, imports, source metadata and diagnostics. Private helpers are
execution support, with `exposed: false`; being a dependency does not select a
public function. Required evidence uses the same selected-scope authority as
exposure planning, including module initialization and incomplete evidence.

For a Data Scientist, this lets an assistant inspect `model.predict`, explain an
unresolved feature-normalization dependency and see a precise import refusal,
while unrelated unfinished experiments remain in the complete repository audit.
Analysis does not execute models or evaluate annotations. The view supplies
evidence for a later exposure-policy proposal; it does not authorize execution.

To explore one logical module instead, use:

```json
{"view":"detail","module":"model"}
```

Module detail retains its own capabilities, states, source metadata, outgoing
relationships, imports and diagnostics. Module names and capability IDs match
exactly: no path filter, fuzzy name matching or implicit selection. Detail
requires exactly one of `module` or `capability_id`; unknown identities yield
`unknown_module` or `unknown_capability`. Filters, `offset` and `limit` are valid
only in detail. All incompatible combinations yield `invalid_arguments`.
Module strings are bounded to 512 characters and capability IDs to 1,024;
pagination accepts strict integers, never strings or booleans.

### Keep canonical identity and read every page

Every reduced view declares `view: "summary"` or `view: "detail"`. Its `identity`
contains the **complete** repository, Catalog and Graph digest objects. Readiness
views also contain `repository_readiness_digest` and `readiness_policy_digest`.
Filtering and paging never change those identities. A view has no canonical
artifact schema version and must not be submitted as a Catalog, Graph or
RepositoryReadinessReport.

Detail returns `page` with `offset`, `limit`, `total`, `returned`, `next_offset`
and `complete`. The default limit is 50 records; the maximum is 200 and the
minimum is 1. `offset` starts at zero and is bounded to 2,147,483,647. Filtering
precedes deterministic ordering, which precedes pagination. Continue with the
returned `next_offset`, the same filter and the full repository digest value:

```json
{"view":"detail","capability_id":"python:model:predict","offset":50,"limit":50,"expected_repository_digest":"<64 lowercase hexadecimal characters>"}
```

A nonzero offset requires that digest. If any included source changes between
pages, the next call yields `repository_changed`; restart at page zero with the
new identity. Changing the filter starts another independent collection, whose
counts and offset describe that filter. There is no persistent analysis cache or
pagination session. Each call discovers once and uses retained static artifacts.
Read until `complete: true` to obtain all ancillary records; focus, decision
states and principal blockers are never paged away.

### Understand a refused exposure plan

`apizr_plan_exposure` retains `isError: true`, `error.code: "exposure_refused"`
and every existing diagnostic field. An additive `action` names a corrective
step when supported by evidence. A dependency refusal can identify:

```json
{"source_path":"config.py","line":1,"dependency_path":["python:serving:predict","python:features:_normalize","python:config:scale","python-module:config"],"evidence_code":"APIZR-GRAPH-002","reason":"import","action":"fix_import"}
```

This is a diagnostic excerpt, not a replacement response schema. Stable actions
include `fix_import`, `fix_binding`, `fix_initialization`,
`select_known_capability`, `resolve_interface_contract`,
`adjust_execution_requirements` and `inspect_dependency`. Unknown evidence has
`action: null`; actions express a suggested correction and grant no authority.

For large refusals, optionally request `limit`/`offset` alongside `policy`.
`error.page` and `error.diagnostic_count` describe the complete deterministic
diagnostic collection. Continuations require `expected_repository_digest`;
successful canonical plans remain unchanged even when paging was requested.

### Request the complete audit when needed

Existing clients calling `{}` receive the same complete canonical fields.
Explicit `{"view":"full"}` returns that same result. Full reports remain useful
for audit/export; summary and detail improve normal assistant conversations.
The advertised output schema accepts each strict response variant.

All modes obey the response limit. A full report exceeding it yields
`response_too_large`; the server never switches silently to a summary. Request a
summary or smaller detail page explicitly. A page can still exceed the byte
limit when an individual record is large. Views contain source metadata and
retained static evidence, never raw source files, host paths or tracebacks.

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
returns `response_too_large`, never a truncated canonical report. Result serialization
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

The real integration proof uses the locked official Python MCP SDK **2.3.0**, its
[low-level API](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/advanced/low-level-server.md),
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

`scripts/mcp_views_proof.py` also measures actual structured response bytes on a
69-file repository, validates every successful view against its advertised
schema through real stdio, reads the complete dependency slice and checks source
changes between pages. Both supported protocols prove that a small response
bound refuses full reports while allowing an explicitly requested summary.

`scripts/mcp_schema_proof.py`, included in the installed-wheel proof, retains
`schemas-auto.json` and `schemas-legacy.json` from actual `tools/list` responses,
plus the corresponding tool results and `schema-proof.json`. It checks property
descriptions, referenced definitions and schema examples, obtains a real digest
from analysis, pins readiness to it, and plans an actually discovered capability.
Its fixture includes uncertain experimental code, so a valid readiness result
has `exit_code: 1` and `isError: false`. Project prose cannot replace its discovery
metadata. The proof runs locally without network access after installation and
does not depend on external directory scoring. `--capture-only` retains prior
discovery/results for before/after comparison without requiring new descriptions.
The compact test baseline records the prior validation-schema and business-result
fingerprints; full discovery JSON stays in qualification artifacts.

The same proof retains `discovery-{auto,legacy}.json` with initialization
instructions and complete tool metadata, and `recovery-{auto,legacy}.json` with
SDK responses including error status. Real changed-source, missing-policy and
refused-selection calls accompany the normal journey. `guidance_baseline.json`
binds the prior installed wheels and fingerprints every unchanged discovery
contract and response, including #268's schema descriptions/examples. Only the
three analysis tool descriptions and initialization instructions are excluded
from discovery comparison. Delivery discovery retains all six tools and verifies
their effect annotations separately in `mcp_delivery_local_proof.py`.

### Local TDQS review

This assessment covers the six Tool Definition Quality Score dimensions without
claiming an external score. `verify_guidance` checks essential selection/recovery
concepts and a conciseness budget against actual SDK discovery; it does not
attempt to measure agent intelligence or directory ranking.

| Dimension | Assessment and check |
| --- | --- |
| Purpose Clarity | Analyze discovers identities, readiness assesses usability, planning tests a chosen proposal. Each description names its distinct result. |
| Usage Guidelines | Each tool states when to choose it and a next step; initialization presents discover → assess → propose as optional guidance. Fresh-session readiness/planning tests preserve independent use. |
| Behavioral Transparency | No project execution or authority grant; fresh evidence, readiness business results, structured refusals, recovery and delivery effects are explicit and exercised. |
| Parameter Semantics | #268's complete schemas, referenced definitions and valid examples remain unchanged, verified against installed discovery fingerprints. Descriptions refer to those schemas. |
| Conciseness | Each analysis description is capped at 115 whitespace-delimited words; initialization at 350 in either mode. Shared workflow/recovery guidance lives in initialization rather than being repeated per tool. |
| Contextual Completeness | Capability IDs, actual digest pinning, policy fallback, startup scope, principal recoveries and mode-specific effects are available without external documentation. |

External Glama evaluations, when available, are dated observations about the
version indexed there. They are not an offline qualification gate or evidence
that an unpublished development commit has been evaluated.

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
