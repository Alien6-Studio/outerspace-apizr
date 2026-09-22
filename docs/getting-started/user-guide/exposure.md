# Plan explicit repository exposure

**Development feature: 0.3.0 (`0.3.0.dev0`). Latest stable: 0.2.1.**
Use a development checkout for these commands; the public PyPI installation
instructions continue to install the stable release. No 0.3 release is published.

Readiness describes eligibility under a policy. Exposure records what the
operator explicitly selects for publication, through which interfaces and under
which execution requirements. It does not generate or start a server.

An exposure plan records an explicit publication decision over static evidence; it is not an authorization grant or runtime safety proof.

## Choose capabilities

For `shop/pricing.py` defining `calculate`, use the exact capability ID displayed
by Scan/Readiness. Declare an interface and at least one allowed execution mode:

```sh
apizr expose plan . --interface mcp --execution-mode oci-container \
  --select python:shop.pricing:calculate
```

Repeat `--select`, `--interface` and `--execution-mode` for multiple choices.
Multiple compatible modes remain in the plan; there is no preferred backend.
`--all-ready` deliberately includes every repository `READY` capability.
`--exclude python:admin:delete_user` always wins over includes. Unknown include
or exclude IDs are errors, including typos in exclusions. Without any selector,
a valid empty plan is returned with a warning in the human report.

## Use policy files

Save `exposure.json`:

```json
{
  "schema_version": "apizr.exposure-policy/v1",
  "selection": {
    "include": ["python:shop.pricing:calculate"],
    "include_all_ready": false,
    "exclude": []
  },
  "interfaces": ["rest", "mcp"],
  "eligibility": {"allow_conditional": false},
  "execution": {
    "allowed": ["local-process", "oci-container"],
    "require": ["wall_timeout"]
  }
}
```

```sh
apizr expose plan . --policy exposure.json
apizr expose plan . --policy exposure.json --plan > exposure-plan.json
apizr expose plan . --readiness-policy readiness.json --policy exposure.json
```

Policy files use JSON. `--policy` cannot be mixed with inline exposure choices;
`--readiness-policy` remains independent. The default readiness policy is the
existing deterministic OSS policy. Its execution modes are local-process and
OCI; to plan direct execution, explicitly include `direct` in both policies:

```json
{"execution": {"modes": ["direct"], "require_controls": []}}
```

That fragment is a **readiness** policy. The exposure policy uses
`"execution": {"allowed": ["direct"]}`.

Inline flags also include `--allow-conditional` and repeated
`--require-control`. Requiring `network_deny` narrows compatible modes to OCI;
`subprocess_deny` cannot be satisfied by any current mode. Docker/image
availability is not checked. No runtime image is part of the plan.

## Read the result

The human report lists total/READY/selected/planned counts, interfaces,
contract-compatible execution counts, selected IDs, retained uncertainty and
observed support/external modules. `--plan` emits only canonical JSON on success.
The artifact binds Catalog, Graph, Repository Readiness and Exposure Policy
by digest, enabling deterministic review across filesystem locations.

- `READY` selections must still satisfy interface and execution requirements.
- `CONDITIONAL` requires explicit opt-in and an eligible shared interface
  contract. The opt-in cannot override unresolved local type/callable contracts.
- `AMBIGUOUS` and `UNSUPPORTED` are always refused.
- Globally incomplete repository evidence is always refused.
- Any refused selection blocks the whole plan. No partial result is published.

If A calls B, selecting A **does not expose B**. The plan keeps the direct
relationship as evidence. Supporting modules are observed direct requirements,
not a complete packaging closure. Effects are copied, never newly inferred or
propagated. External module names are lexical evidence without environment
resolution or package classification.

## Exit codes and bounds

| Exit | Meaning | Output |
| --- | --- | --- |
| 0 | Valid plan, including an empty plan | Human report or canonical JSON on stdout |
| 1 | Selection/evidence/policy refusal | Deterministic diagnostics on stderr; no plan bytes |
| 2 | Invalid policy, malformed ID, invalid/inaccessible repository input | Sanitized error on stderr; no plan bytes |

Argument-parser errors also exit 2. Bound discovery/graph failures that yield
incomplete evidence exit 1. All existing scan/graph bounds are available:
`--source-root`, `--exclude-dir`, file/total/entry/depth limits and AST,
relationship, call and import limits. Each source is discovered/read once;
planning does not rescan it.

`apizr expose build` and `apizr expose serve` do not exist yet. Continue to use
the existing individual REST/MCP generators separately. Repository-level
bundles are tracked in [#88](https://github.com/Alien6-Studio/outerspace-apizr/issues/88).
See [Exposure Plan v1](../../architecture/exposure-plan-v1.md) for model, schema,
serialization, digest and validation details.
