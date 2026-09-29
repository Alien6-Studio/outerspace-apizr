# Proof-required delivery admission

For a proof-required delivery, Apizr may transfer the image to obtain its immutable
digest, but it withholds promotion to the requested destination tag until an
explicitly selected remote proof has been independently verified.

Image transfer is not delivery admission. Registry blobs, manifests and random
`apizr-upload-*` staging tags may already exist. Apizr does not delete them,
claim rollback, control registry garbage collection, or prevent another registry
writer from exposing that digest.

## Select the requirement before building

Set `proof_requirement` to `required` in the existing `apizr.oci-build/v1`
arguments and in the exact operator `build` grant's `target`. Both default to
`optional`. The existing `image.build` and `registry.read` permissions remain
necessary. A grant for an optional target cannot authorize a required target,
or vice versa. Project configuration, plugin activation and catalog profiles
cannot supply operator authority.

The frozen `DeliveryPlan` includes the requirement in its canonical identity.
Changing it to `required` changes the plan digest, build inputs and image labels.
Optional is omitted from canonical plan JSON to preserve historical plan digests.
The builder verifies `sh.outerspace.apizr.proof-requirement` and the existing
plan/input labels on the built image.

Pass both `delivery_plan` and `delivery_manifest` from the BuildResult to the
existing `push` request. For required images, omitting either, substituting an
optional plan, or removing lineage fails before upload. A required push verifies
the immutable remote digest but does not promote the requested destination tag.
An optional push retains normal destination promotion and needs no Attest plugin.

## Explicit states

`PushResult.published:true` retains its historical image-publication meaning.
New push results also report:

| Field | Optional push | Required push |
| --- | --- | --- |
| `proof_requirement` | `optional` | `required` |
| `transfer_verified` | `true` | `true` |
| `destination_promoted` | `true` | `false` |
| `delivery_admitted` | `false` | `false` |

Only the admission result confirms proof-gated admission. Historical results
without these fields remain valid; no proof-admission state is invented for them.
A required push does not claim it promoted a tag even if another operation has
already made the same digest reachable there. Existing conflicting destinations
are still refused before transfer.

## Sign, publish, explicitly select, admit

Use the existing `attest` operation against the transferred digest, without
requiring a destination tag. Publish its seven-file transversal proof through
`publish`. Historical six-file proof verification remains supported, but cannot
admit a delivery whose required lineage is absent.

Select one exact `artifact_reference`, normally from a verified PublishResult.
After uncertain publication, use `discover`, inspect the candidates, then select
one explicitly. Discovery never chooses a candidate, and admission never retries
proof publication. A local PublishResult is not admission evidence.

Invoke the installed `outerspace-apizr-attest` plugin's `admit` operation with:

- `schema: "apizr.admit-delivery/v1"`;
- `push_result`: absolute path to the original required PushResult;
- `delivery_manifest`: the expected immutable manifest object;
- `destination`: the originally requested destination tag;
- `expected_reference`: the exact transferred image digest reference;
- `artifact_reference`: the explicitly selected proof digest in that repository;
- `expected_signer`, `trust_store`, `tool`: independently selected Attest trust
  and pinned native binary, as for `verify`;
- `transport`: pinned ORAS binary and explicit registry authentication, as for
  `fetch`;
- `docker`: explicit Docker executable, socket and optional Buildx binary;
- optional bounded `timeout_ms` and `max_output_bytes`, as for other proof operations.

```shell
apizr plugins run outerspace-apizr-attest admit \
  --arguments /operator/admit.json \
  --operator-policy /operator/permissions.json \
  --plugins-dir /operator/plugins
```

The managed operator grant must bind the exact installed Attest identity and
locked closure, operation `admit`, exact registry repository, and both
`registry.read` and `registry.publish`. A `publish` or `attest` grant does not
allow `admit`. No private signing key, `receipt.sign`, or `timestamp.request`
permission is needed. The core only validates shared contracts and permissions;
it does not import native proof support.

Admission independently retrieves the image and selected referrer, checks
referrer discovery and descriptors, fetches every bounded/hash-verified proof
blob, and reuses the native verification stack. All five checks must pass:
schema, consistency, signature, timestamp and recomputation. Warnings and skips
fail closed. It verifies the expected manifest, signed build/push lineage,
required plan, remote config/platform/user and input/plan/requirement labels.

Only then does it inspect the destination. An absent tag is promoted from the
exact immutable digest, an identical destination is verified idempotently, and
a conflicting image is refused. It re-observes destination and immutable digest
after promotion. It never rebuilds, uploads application layers during admission,
or selects a mutable local tag.

`apizr.delivery-admission/v1` with `state:"admitted"` records the destination,
image digest reference, plan and manifest digests, proof artifact reference and
manifest digest, receipt SHA-256, expected signer and three explicit state fields.
This terminal observation contains no operational paths or secrets and is not an
input to the image or DeliveryManifest; the identity graph remains acyclic.

## Uncertainty and recovery

A failure before promotion returns no admission success. A caught error after
promotion starts returns `state:"remote_state_unconfirmed"`,
`delivery_admitted:false`, `destination_promoted:null`. Transfer remains verified;
proof verification does not establish whether the tag mutation completed.
A forcibly stopped worker cannot return a result: `cancelled`/timeout likewise
must be treated as unconfirmed remote destination state, never rollback.

Retry with the same explicit proof identity. Admission re-fetches and verifies
proof, then inspects the destination; if already identical it can complete
idempotently. No remote data is deleted as compensation. Registry tag updates
are not compare-and-swap: an external concurrent writer can race or subsequently
change a tag. The admission record describes the verified observation, not a
permanent lock on that tag.

The disposable HTTPS registry qualification retains `admission-results.json`
and `admission-refusals.json`: REST/MCP checkpoints before admission, negative
proof checks, post-promotion uncertainty and recovery, exact destination digests,
and signing-key absence. The existing independent consumer fetches and verifies
the proof offline. Services run from the recorded digests after original source
and bundles are removed, with no source mounts.

See [multi-destination delivery](multi-destination-delivery.md) for sequential managed orchestration, independent outcomes and explicit resume of one immutable build.
