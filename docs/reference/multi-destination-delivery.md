# Multi-destination delivery

`apizr delivery run` delivers one already-built, qualified image to **1–8 explicit
OCI destinations**, sequentially in request order. It invokes the installed OCI
and Attest plugins through the managed extension runtime. It never calls build,
regenerates a bundle, resolves dependencies, or changes the DeliveryPlan or
DeliveryManifest. Every destination must carry the same image ID, platform,
`inputs_sha256`, plan and manifest. Equivalent destinations, including the
`index.docker.io` alias, are rejected before the first effect.

## Request and CLI

The Python API is `apizr.delivery_batch.deliver_batch(BatchRequest, ...)`.
The CLI uses the same coordinator:

```sh
apizr delivery run --request delivery.json \
  --operator-policy operator.json --plugins-dir /absolute/plugins
apizr delivery resume --request delivery.json \
  --operator-policy operator.json --plugins-dir /absolute/plugins
```

`delivery.json` uses schema `apizr.delivery-batch-request/v1` with:

- `build`: the existing successful `apizr.oci-build-result/v1`, including its
  DeliveryPlan, DeliveryManifest and manifest digest;
- `destinations`: an ordered array of 1–8 objects;
- `evidence_root`: an explicit absolute private directory for retained evidence.

Each destination contains `push`, the existing `apizr.oci-push/v1` request, with
that exact build identity, the final destination, explicit Docker executable and
socket, and its own authentication/CA files. The coordinator does not discover or
merge credentials and never inherits the user's Docker configuration.

For an optional plan, omit `proof`; the `oci` profile is sufficient. For a required
plan, every destination supplies `proof` and needs the `delivery` profile:

| Proof input | Existing contract fields |
| --- | --- |
| `verification` | `expected_signer`, `trust_store`, pinned `tool`, optional `timeout_ms` and `max_output_bytes` |
| `signing` | `key_file`, `key_id`, `tsa_url` |
| `transport` | Existing ORAS transport, with pinned tool and this destination's authentication/CA files |

The coordinator supplies build/push evidence paths, the exact digest reference
returned by transfer, and a safe proof output subdirectory. These are operational
inputs, not portable delivery identity. Signing/trust inputs can be shared
explicitly; credentials remain independently selected for every destination.

## Independent authority and proof

Every effect goes through `run_extension`, with the normal exact installed plugin
identity and locked closure. A request or profile grants no authority.

| Operation | Required exact repository grant |
| --- | --- |
| OCI `push` | `registry.read`, `registry.publish` |
| Attest `attest` | `registry.read`, `receipt.sign`, `timestamp.request`, exact key, signer and TSA |
| Attest `publish` | `registry.read`, `registry.publish` |
| Attest `admit` | `registry.read`, `registry.publish` |
| OCI `observe` on resume | `registry.read` |

`observe` is a read-only managed operation using the existing OCI remote identity
observer. Its `apizr.observe-delivery/v1` request contains `push` and an optional
`expected_reference`; it reports `apizr.delivery-observation/v1`. This separate
operation lets resume check a destination without replaying publication. Grants
for another operation, repository or installed identity do not authorize it.
There is no wildcard batch grant and partial grants are not combined.

Optional delivery completes after the existing push has verified promotion and
re-observed the destination. Required delivery completes only after this
repository's transfer, signing/timestamping, proof publication and independent
admission. The coordinator passes the exact artifact from that successful
publication to `admit`; it never selects a discovered candidate. A proof for A
does not authorize B. The five native checks and independent trust remain intact.

## Results and failure

Standard output is an `apizr.delivery-batch/v1` JSON result, even on partial
failure. It binds the common DeliveryManifest and digest, proof requirement and
one typed outcome per requested destination, in request order.

| Aggregate state | Meaning | Exit status |
| --- | --- | --- |
| `complete` | Every destination reached its required terminal state | 0 |
| `partial` | At least one completed and at least one did not | 1 |
| `failed` | None completed | 1 |
| `cancelled` | Caller cancelled the batch; retained outcomes remain explicit | 130 |

Preflight input/evidence refusal exits 2 with a fixed diagnostic and no delivery
effect. Destination outcomes distinguish `not_started`, `complete`, `failed` and
`remote_state_unconfirmed`, plus a separate `last_confirmed_stage`:
`not_started → transferred → proof_created → proof_published → admitted` for a
required plan, or `not_started → transferred → complete` for an optional plan.
Typed transfer, proof, publication and admission records retain the exact per-repo
identities. An incomplete outcome has a fixed diagnostic; no raw native error,
credential, key, trust path or arbitrary exception string enters the aggregate.

B's refusal does not discard A or stop C. There are no automatic retries or remote
rollback. The runtime deliberately redacts plugin errors; where it cannot prove
that a mutating call had no effect, the coordinator conservatively records remote
uncertainty rather than guessing from Docker/ORAS stderr.

## Evidence and resume

The explicit evidence root retains `build.json`, `batch.json` and a bounded
SHA-256-named subdirectory for each normalized destination. Each subdirectory
contains `push.json` and the existing exported `proof/`. Portable aggregate records
contain no local paths. Evidence uses private regular files, refuses symlinks or
conflicting immutable evidence, and serializes writers under a bounded lock.
Use a resolved absolute root path (for example `/private/tmp/...` on macOS).

Resume requires the same build, plan/manifest identity, proof requirement and
exact ordered destination set. Credentials, trust and tool paths can be supplied
again explicitly. The build and immutable transfer files cannot be overwritten by
a different record. Stage progress is checkpointed before mutating calls and
again after confirmed results; this is not a distributed transaction.

- Completed destinations are observed again. Missing or conflicting final tags
  become incomplete; an old admission never permanently locks a tag. Required
  destinations reverify the same selected remote proof through `admit`, without
  signing or publishing again.
- A retained transfer is independently observed and reused without uploading the
  image again. A retained local proof is independently verified and reused without
  signing a second receipt.
- A verified publication supplies its exact artifact identity for admission.
- After uncertain proof publication, the coordinator stops with
  `proof_selection_required`. Use existing discovery, inspect/select a candidate,
  then set that destination's `selected_artifact` explicitly and resume. No
  automatic discovery selection or blind republication occurs.
- After uncertain transfer without a known immutable digest, resume first observes
  the destination. If it cannot establish the image, it stops with
  `transfer_identity_required`. Inspect the registry and supply this destination's
  explicit `recovery_reference`; the read-only observer must verify it. The existing
  push operation's optional `resume_reference` permits verified digest promotion
  without another layer upload. It still validates local identity and exact grants.
- Uncertain admission first observes remote state, then reverifies proof and uses
  existing idempotent admission. It never treats uncertainty itself as completion.

Cancellation stops later destinations, preserves recorded progress and does not
roll back prior effects. Existing operation cleanup deadlines are unchanged.
A hard process crash or failed local write can leave remote state or incomplete
local evidence. Failure of the shared evidence store can also prevent aggregate
output; it does not imply that no remote effect occurred. Explicit inspection may
then be necessary. Killing the core does
not undo work already accepted by a Docker daemon or registry.

## Qualification and scope

The existing disposable authenticated HTTPS registry/TSA/Attest/ORAS fixture now
uses three independent repository credential scopes for both REST and MCP. A and
C complete while B's signing key is unavailable; the aggregate is `partial`.
Restoring only B's key and resuming produces `complete`, with no rebuild or upload
and only B signing a new receipt. Managed-call traces, Docker build observations,
TSA request counts, pre-admission tag absence and per-destination remote identities
are retained in the fixture artifacts. The services then run from the batch's
recorded digests after original sources and bundles are removed. Existing
independent offline proof verification is preserved.

Single-destination APIs and historical evidence remain supported. Versions remain
`0.4.1rc1`. This increment adds no concurrent delivery, cross-repository proof reuse,
production registry adapters, MCP delivery tools, rollback or automatic proof
selection. Live-provider qualification, including Docker Hub, is optional
interoperability validation; it is not a remaining 0.4.1 functional requirement.
The fixture establishes the documented OCI registry profile, not compatibility
with every registry implementation.
