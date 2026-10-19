---
title: MCP distribution qualification
description: Local qualification and public verification of the official Apizr MCP plugin.
---

# MCP distribution qualification

This guide covers distribution of the official **0.4.6** MCP plugin,
`io.github.Alien6-Studio/outerspace-apizr`, supplied by `outerspace-apizr-mcp`.
Generated business servers have their own contracts. Local qualification and
external directory acceptance are verified separately; a prepared bundle alone
is not proof of publication.

Users start at [Registry installation](../reference/apizr-mcp-server.md#registry-installation).
All three explicit inputs remain required, with no defaults: a selected project,
reviewed source-analysis grant and installed/activated plugin store. No registry,
bundle, schema or ExposurePolicy grants runtime authority.

## Current sources and decisions

Inspected **2026-10-11**. Ordinary CI consumes the retained schemas in
`tests/fixtures/mcp_distribution`, verifies their origin hashes and makes no
directory requests. Remote documentation is not a test dependency.

| Primary source | Revision/version inspected | Requirement used |
| --- | --- | --- |
| [Official server.json](https://github.com/modelcontextprotocol/registry/blob/970df037919faa70456dde08c295473002d850e5/docs/reference/server-json/generic-server-json.md), [changelog](https://github.com/modelcontextprotocol/registry/blob/970df037919faa70456dde08c295473002d850e5/docs/reference/server-json/CHANGELOG.md) | Registry `970df037919faa70456dde08c295473002d850e5`; published schema `2025-12-11` | Keep the accepted published schema; do not adopt the unreleased draft. Validate the full descriptor offline. |
| [Additional registry requirements](https://github.com/modelcontextprotocol/registry/blob/970df037919faa70456dde08c295473002d850e5/docs/reference/server-json/official-registry-requirements.md), [PyPI ownership](https://github.com/modelcontextprotocol/registry/blob/970df037919faa70456dde08c295473002d850e5/docs/modelcontextprotocol-io/package-types.mdx) | Same registry revision | Public PyPI identity, exact namespace and README ownership marker; no alternate package registry. |
| [Publisher](https://github.com/modelcontextprotocol/registry/releases/tag/v1.8.1), [validate implementation](https://github.com/modelcontextprotocol/registry/blob/970df037919faa70456dde08c295473002d850e5/cmd/publisher/commands/validate.go) | `v1.8.1` | Keep the pinned publisher/checksum and GitHub OIDC. `validate` is non-publishing but calls the registry API; it is not an offline CI step. |
| [MCP tools 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | Locked Python SDK `2.3.0`, both qualified protocols | Use canonical `Tool.title`; retain typed schemas and existing annotations. The installed client verifies both modes/protocols. |
| [Glama schema](https://glama.ai/mcp/schemas/server.json), [ownership metadata](https://glama.ai/blog/2025-07-08-what-is-glamajson), [read API](https://glama.ai/api/mcp/openapi.json) | JSON Schema draft-07; API `1.0.0` | Keep the existing maintainer-only `glama.json`. Directory reads need a key. No invented fields or automatic ownership-claim/re-index action. |
| [Smithery publication](https://smithery.ai/docs/build/publish), [stdio publication API](https://smithery.ai/docs/api-reference/servers/publish-a-server), [download API](https://smithery.ai/docs/api-reference/servers/download-server-bundle) | API `1.0.0` | Local stdio publication uses an MCPB upload. There is no documented guarantee of automatic Official Registry ingestion. Prepare a bundle; do not add legacy `smithery.yaml`. |
| [MCPB manifest](https://github.com/modelcontextprotocol/mcpb/blob/70fe3b34cd6dff1b3bba046638edc72a6467a4fb/MANIFEST.md) | `70fe3b34cd6dff1b3bba046638edc72a6467a4fb`, manifest `0.4` | Standard `uv` runtime with pinned package, explicit user configuration and a delegating entry point. Host support and actual Smithery acceptance must be confirmed in Phase B. |
| [MCPfinder](https://github.com/mcpfinder/mcpfinder/tree/abcdab08862535ab84673edb241209c714a5b748) | `abcdab08862535ab84673edb241209c714a5b748` | Secondary union of Official Registry, Glama and Smithery. Use its documented digest-bound snapshot; the former HTTP MCP endpoint is deprecated. |
| [Is It Trust-Ready? rubric](https://www.isittrustready.ai/rubric), [machine-readable rubric](https://www.isittrustready.ai/rubric.json) | `0.6.2` | Apply the ten MCP-axis criteria below. No fabricated score or third-party pass. |

## Six-tool review

All descriptions explain purpose and use; the existing delivery descriptions also
identify effects and retry limitations and need no expansion. #268/#269 analysis
descriptions, examples and initialization instructions are retained. Only the
previously undocumented delivery manifest pin gains a field description; its
nested `Digest.algorithm` and `Digest.value` were already documented.

| Stable name | Human title | Input contract | Output | Hints: read-only / destructive / idempotent / open-world |
| --- | --- | --- | --- | --- |
| `apizr_analyze` | Analyze Python Project | Strict described views/pin | Analysis union | true / false / true / false |
| `apizr_readiness` | Assess Repository Readiness | Strict described views/pin | Readiness union | true / false / true / false |
| `apizr_plan_exposure` | Plan Capability Exposure | Strict described policy/pin/paging | ExposurePlan | true / false / true / false |
| `apizr_delivery_status` | Inspect Delivery Status | Explicit empty object, unknown fields forbidden | BatchResult | true / false / true / false |
| `apizr_delivery_run` | Run Approved Delivery | Strict described manifest digest object | BatchResult | false / false / false / true |
| `apizr_delivery_resume` | Resume Approved Delivery | Strict described manifest digest object | BatchResult | false / false / false / true |

Status only reads retained local evidence. Run/resume can write local evidence
and remote images/proofs under captured per-operation authority. Their current
operations perform no remote deletion or rollback and refuse conflicting observed
image identities; registry preflight is not an immutable-tag or compare-and-swap
guarantee. Non-idempotent/open-world hints preserve that distinction. Hints are
presentation information, never authorization controls.

## MCP trust-readiness alignment

Each row is a local assessment, not a claim that an external scanner ran.

| Criterion (`mcp.cap.*`) | Applicable | Apizr evidence | Test/proof | Remaining external dependency |
| --- | --- | --- | --- | --- |
| `tool-descriptions` | Yes, all six | Fixed purpose/use/effect descriptions | `mcp_tool_metadata.review`, #269 guidance checks | Directory re-indexing |
| `param-descriptions` | Yes; status has no parameters | Every input property, including nested digest/policy/view types, described | Recursive live schema review | Directory schema refresh |
| `output-schemas` | Yes, all six | Canonical output schemas; business failure remains distinct from MCP failure | Actual SDK results validated against advertised schemas | Directory visibility of schemas |
| `typed-bodies` | Yes | Strict objects and unknown-field rejection; status deliberately takes `{}` | Schema and invalid-argument tests | None locally |
| `titles` | Yes, all six | Standard `Tool.title` | Both protocols, both initialization modes, installed wheels | Client/index title support |
| `annotations-present` | Yes | All four hints present | Live SDK assertions | Directory refresh |
| `annotations-justified` | Yes | Static analysis; local status; effectful delivery | Existing non-mutation, admission, lifecycle and delivery proofs | None locally |
| `server-metadata` | Yes | Stable machine name, human title/version/instructions; registry description/homepage/existing icon | SDK discovery, descriptor/schema/package checks | Released descriptor and icon accessibility |
| `naming` | Yes | Existing consistent `apizr_*` snake_case | Exact six-name contract | No vendor-driven rename |
| `config-ux` | Yes | Three described, required file inputs and documented acquisition | Document-derived new-user fixture and installed registry launch | Actual directory configuration UI |

The rubric's generic “empty properties” heuristic is inapplicable to the
intentionally argument-free status tool: `{}` with `additionalProperties: false`
is an exact typed contract. Security-sensitive configuration has no safe default.
Website/domain signing, hosted OAuth and remote server-card checks are outside
this local stdio MCP-axis qualification; no hosted service is invented to score them.

## Offline evidence and compatibility

`scripts/mcp_schema_proof.py` and `scripts/mcp_delivery_local_proof.py` retain real
SDK discovery and successful structured responses, including valid limited/failed
business outcomes. The #268/#269 fingerprints still constrain schemas, outputs,
errors and annotations. The compatibility projection removes only the six new
tool titles, the human server title and the two delivery pin descriptions. Modern
SDK response metadata may also carry that server title; business content and
digests remain unchanged. Hostile project/result prose cannot change any trusted
metadata. Full raw captures remain in the existing native MCP CI artifacts.

`scripts/mcp_registry_proof.py` launches `uvx` with committed descriptor arguments,
candidate wheels outside checkout and no package-index access. Its new-user input
fixture comes from this guide's marked examples, not implementation internals.
It verifies both protocols, titles/annotations, live output schemas, and refused
missing/invalid project, policy and store inputs. The MCPB wrapper undergoes the
same offline installed launch. It cannot enable delivery or bypass plugin admission.
Its runtime is first installed from the unchanged bundle `pyproject.toml` using
only that target's retained wheels; `UV_NO_SYNC=1` then prevents universal
re-resolution across unavailable Python/platform wheels during the offline launch.
The public bundle keeps normal `uv run` dependency preparation. Its declared
resolution environments match its macOS/Linux support, using the documented
[uv project setting](https://docs.astral.sh/uv/concepts/projects/config/)
(inspected 2026-10-11, qualification uv 0.12.0). Real directory-host installation
remains a separate Phase B check.

Build the deterministic local bundle without submission:

```sh
uv run --locked python scripts/build_mcp_bundle.py --output /tmp/outerspace-apizr-0.4.6.mcpb
```

This is a separate launcher wrapper, not a new Python publication or a substitute
for the governed plugin store. No wheel/sdist version or dependency lock changes.

## External verification after authorization

Use the qualified candidate manifest and installed analysis discovery capture:

```sh
uv run --locked python scripts/verify_mcp_distribution.py \
  --source-sha <QUALIFIED_RELEASE_SHA> \
  --candidate <RELEASE_CANDIDATE_DIRECTORY>/candidate.json \
  --discovery <MCP_PROOF_DIRECTORY>/discovery-auto.json \
  --output /tmp/mcp-distribution.json
```

This default performs **no network access**; providers are `not_checked`.
After release, add `--live`, optionally `--include-mcpfinder`,
`--smithery-name <NAMESPACE/SERVER>` and
`--smithery-bundle <QUALIFIED_MCPB_FILE>`. The name must be the stable name actually
chosen during authorized Smithery publication, never a guessed temporary ID.
`--require-complete` exits nonzero while any proof is incomplete. The tool never
publishes, claims ownership, scans a project or triggers indexing.

States distinguish `verified`, `stale`, `missing`, `mismatch`, `not_checked`,
`authentication_required` and `temporarily_unavailable`. Every non-verified state
also reports `verification: not_verified`. A timeout, authentication failure,
unsupported response or malformed payload is never reported as absence or success.
No polling loop is needed: maintainers may rerun this explicit read-only step as
propagation progresses, retaining each timestamped report.

- **PyPI:** require both core and MCP 0.4.6, the exact qualified wheel/sdist hashes,
  non-yanked files and the MCP namespace marker. Package version alone is insufficient.
- **Official Registry:** require the exact active name/version, repository, PyPI
  package, stdio transport and released configuration/metadata. Differences fail
  distribution qualification.
- **Glama:** directory reads use `GLAMA_API_KEY`. The current API exposes names,
  descriptions and input schemas, but not titles, output schemas, initialization
  or package/version. Compare available fields, then review the public
  [schema page](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr/schema)
  for additional exposed fields and retain dated evidence. API-only verification
  cannot establish a complete 0.4.6 pass. Missing credentials stay unverified.
  Reports using its data credit and link Glama. Any ownership claim or indexing
  action requires the separate Phase B authorization.
- **Smithery:** use `SMITHERY_API_KEY` to read the actual qualified listing and
  download its MCPB through the documented API. Compare the exact reproducible
  bundle (binding version/repository/package), tools and three required configuration
  inputs. The publication route is a manual MCPB submission, not assumed ingestion.
  The documentation's `uv` MCPB support must be confirmed in the real client:
  Smithery's read API still enumerates older runtime labels. No live compatibility
  claim is made before that submission/installation test.
- **MCPfinder:** inspect its timestamped, hash-verified snapshot through a bounded
  read-only SQLite query. Require the expected package/version/transport and all
  three primary sources, avoiding a stale or single-source confirmation. This is
  propagation evidence, not another publication target. Its documented 18-hour
  snapshot freshness bound is enforced.

The prepared `Verify MCP distribution after release` workflow is manual only,
restricted to `master`, and bounded to 15 minutes with no polling loop. It first
requires the public release preflight and a successful MCP qualification run at
the exact source SHA, then downloads that run's discovery capture. Directory keys
come only from GitHub Actions secrets in its read-only verification step. The CLI
does not consume these keys outside Actions. Keys are neither printed nor retained
in artifacts. Ordinary CI has no directory keys, queries or propagation waits.
The manual workflow retains incomplete reports and exits nonzero while evidence
is missing; it does not run during ordinary CI.

## Additional directories

| Directory | Current classification | Decision |
| --- | --- | --- |
| MCPfinder | Automatic upstream aggregation (Tier 2) | Verify propagation only; do not submit. |
| [PulseMCP](https://www.pulsemcp.com/api) | Official Registry integration plus crawling and manual curation/submission | Optional useful curated reach; first check upstream propagation. A later manual submission is a separate choice. |
| [mcp.so](https://mcp.so/submit) | Current self-service paid submission | No submission recommended for this qualification; no evidence it adds required technical coverage. |

PulseMCP's direct page fetch was access-limited during review; its public indexed
API documentation describes the maintained integration/submission path. No claim
is made that either optional directory has accepted this candidate. No mass
directory submission or website/domain work belongs to Phase A.

## Publication preflight

The manual `Publish MCP Registry` workflow remains restricted to `master` and
retains GitHub OIDC and the verified publisher binary. Before authentication,
both manual workflows admit the requested tag/SHA against the published release
and protected master history in an inline step **before checkout**. This prevents
an arbitrary candidate from supplying the code that decides its own admission.
`scripts/verify_mcp_publication.py` requires a clean checkout at the full requested
SHA, a matching existing release tag, published final GitHub Release, source in
protected master history, qualification assets, matching release archive digests,
and the actual public PyPI identities/hashes/ownership marker. It cannot publish.
The publisher's own online `validate` follows this preflight, then the separately
authorized publish step. Normal Phase A CI exercises guards with offline fixtures;
it does not dispatch that workflow.

Follow the [release sequence](releases.md#dated-directory-verification-after-authorized-publication)
with maintainer authorization. Retain dated public verification with the release;
record missing credentials or delayed directory propagation explicitly.
