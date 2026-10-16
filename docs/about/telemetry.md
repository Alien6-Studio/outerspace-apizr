# Telemetry: local preview and public contract

Apizr 0.4.6 development keeps telemetry **off by default** in the CLI, Python SDK,
VS Code and CI. This implementation contains a public receiving contract and an
explicit local preview. After explicit consent, clients count only the approved
operations in bounded process-local memory. There is no event spool, installation
identifier or sending code. Opt-in cannot enable production transmission.

```bash
apizr telemetry status
apizr telemetry enable
apizr telemetry preview
apizr telemetry disable
```

Both commands operate without a project or experiment store. `preview` returns
an envelope containing the planned endpoint, consent request, context restriction,
the effective `collection_enabled` state, `transmission_available: false` and `payload`.
`payload` is a JSON string containing the **exact report bytes**, excluding its
terminal newline. A new `preview` process has an empty report because reports are
never persisted between processes:

```json
{"schema_version":"apizr.telemetry/v1","context":"cli","events":[]}
```

The Python equivalent is explicit and local:

```python
from apizr.telemetry import preview

result = preview(context="sdk", environ={})
assert result["collection_enabled"] is False
assert result["transmission_available"] is False
```

`enable` and `disable` save only `schema_version` and an `enabled` boolean in a
per-user consent file (macOS: `~/Library/Application Support/Apizr/telemetry.json`;
Linux: `$XDG_CONFIG_HOME/apizr/telemetry.json` or `~/.config/apizr/telemetry.json`;
Windows: `%APPDATA%/Apizr/telemetry.json`). It is limited to 512 bytes and written
atomically with mode 0600. `APIZR_TELEMETRY_CONFIG` selects an absolute operator-owned
location for testing or managed preferences. Invalid, symlinked, nonregular or
oversized preferences fail closed. Project files never grant consent.

`APIZR_TELEMETRY=1` requests consent without creating a preference file. An explicit
saved disable, `APIZR_TELEMETRY=0`, a CI/served/runner context or
`APIZR_TELEMETRY_ALLOWED=0` wins over opt-in. Disabling immediately discards active
local counters. No event data enters the consent file or experiment store.

To preview the actual counters of one CLI operation, explicitly request a local
stderr preview (outside CI):

```sh
APIZR_TELEMETRY=1 APIZR_TELEMETRY_PREVIEW=1 apizr experiment inspect model.py
```

Normal stdout and exit status are preserved; stderr adds one
`APIZR_TELEMETRY_PREVIEW` JSON envelope. The wrapper records only the approved
operation and its coarse outcome. Collection or preview failures cannot change
the command's result. The SDK equivalent is an explicit `telemetry.capture()`
context: call `usage.preview()` inside it to inspect the exact report before the
scope clears its memory. Finalized tracking sessions contribute only one
`capture_session` counter, never their parameters, metrics or Run identity.
There are at most 1,000 observed calls per scope and 32 active scopes per process;
further observations are dropped. No persistent queue, retries or network client
exists.

The planned destination is `https://telemetry.outerspace.sh`, operated by Alien6
Studio, with intended EU hosting and no third-party processor. **That infrastructure
is not represented as deployed or qualified.** Production transmission is unavailable
until the private collector, retention, access and deletion procedures have been
qualified in [#335](https://github.com/Alien6-Studio/outerspace-apizr/issues/335)
and a subsequent release enables it. There is no client
credential or token in this public contract.

## Approved policy

The maintainer approved this policy on **2026-10-16**, recorded in
[#316](https://github.com/Alien6-Studio/outerspace-apizr/issues/316). It defines
the allowed events and privacy boundaries for the remaining client work in #317.
This approval does not enable collection or transmission. The current release
still has no sending code, and production activation requires #335 and a
subsequent release.

| Allowed operation | Product decision informed |
| --- | --- |
| `inspect` | Prioritize the first static inspection journey and refusal guidance. |
| `history_list`, `history_show`, `history_diff` | Prioritize history navigation and comparison usability. |
| `capture_session` | Prioritize SDK session usability and refusal guidance. |
| `generate_rest`, `generate_mcp` | Prioritize support for the two generated interfaces. |

Each entry contains only an operation, a coarse `success`, `refused` or `failed`
outcome, and a count. No exception message or diagnostic is included. The report
adds only `schema_version` and `context` (`cli`, `sdk` or `vscode`). Source code,
paths, filenames, experiment names, parameters, scientific metrics, traces, Run
digests, environment details, timestamps and user or installation IDs are excluded.
There is no free-form field. Counts describe calls, not installations or persons;
this contract cannot measure unique participating installations or people.

Client controls are tracked in
[#317](https://github.com/Alien6-Studio/outerspace-apizr/issues/317): explicit
enable/disable, bounded in-memory aggregation, status and exact preview. CI and
generated services never opt in. VS Code's global
`telemetry.telemetryLevel` and `isTelemetryEnabled` API restrict the Apizr choice: the stricter
decision wins and every child engine inherits it through
`APIZR_TELEMETRY_ALLOWED=0`. Usage requires global level `all` and the separate
`apizr.telemetry.enabled` setting. The preview honors these restrictions and any
truthy `CI` value, independently of `APIZR_TELEMETRY=1`.

There is no local event retention beyond the command/capture scope lifetime;
disabling discards its counters. The extension keeps only the last bounded preview
in memory for its window lifetime and clears it on opt-out. Server retention,
IP/proxy logging, deletion, access and approved aggregate indicators require the
private qualification in #335. No retention duration or deployed privacy control
is claimed here. Website consent-gated analytics remain a separate system.

## Receiving contract and reusable conformance fixtures

The [closed v1 schema](../specs/apizr-telemetry-v1.schema.json) rejects unknown
fields at every object level. Reports are UTF-8 JSON, at most 16,384 bytes,
32 event rows, 512 lexical nodes and depth 8. Each count is an integer from 1 to
1,000; an aggregate is at most 1,000 calls and cannot repeat an operation/outcome
pair. These last two semantic constraints are enforced by admission in addition
to the JSON schema. Unsupported versions, duplicate keys, non-finite values and
oversized or structurally excessive reports are rejected with a fixed error.

Reusable accepted and rejected requests live in
`tests/fixtures/telemetry/conformance.json`. They contain synthetic aggregates,
not collected usage. The later private collector must pass these same fixtures.

```bash
# Regenerate the public schema.
python -m scripts.qualification.interfaces.telemetry_contract --export-schema
# Disposable CI receiver: prints an ephemeral loopback URL and stores no bodies.
python -m scripts.qualification.interfaces.telemetry_contract
```

The stub accepts `POST /` with one bounded `Content-Length` and
`Content-Type: application/json`. It returns 204 for an admitted report, 400 for
invalid content/framing and 413 for an invalid size. It does not log requests,
retain bodies or forward anything. CI tests post the CLI preview's exact payload
to this loopback stub; they never target production.

`APIZR_TELEMETRY_TEST_ENDPOINT` changes the preview destination **only** to an
explicit HTTP loopback IP and port, without DNS resolution. Other destinations,
credentials, query strings and fragments are refused. This is a conformance-test
override, not a production opt-in or a sender.
