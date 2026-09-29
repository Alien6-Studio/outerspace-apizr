# Delivery identities

The unpublished 0.4.1 line composes the existing repository and publication
contracts into immutable records. It does not grant operator permissions or
claim that Attest supervised the build.

## Identity graph

```text
source + catalog + graph + policies + readiness + exposure + application
  → validated REST/MCP BundleManifest (including artifact hashes)
  + inspected, hashed wheel closure + installed tool versions + build target
  → DeliveryPlan → canonical plan digest → OCI image label and build inputs
  → observed image ID/platform/inputs → DeliveryManifest → manifest digest
  → PushResult → Attest proof-binding manifest → signed/timestamped receipt
```

`DeliveryPlan` forbids observed images, destinations and proof fields.
`DeliveryManifest` forbids push outcomes, tags, destinations, receipt hashes,
proof artifact references and proof-manifest digests. Both use frozen value
models, forbid extra fields and have separate schemas. A second destination
therefore cannot change the manifest of an already built image.

## Existing identities and canonical bytes

Repository `canonical_bytes` and `Digest.of_bytes` remain the serialization and
SHA-256 primitives: sorted object keys, compact UTF-8 JSON, no NaN, final newline.
The older Attest proof-binding serializer remains unchanged for compatibility.

The plan binds catalog, graph, scan policy, graph policy, readiness policy/report,
exposure policy/plan, repository interface and bundle manifest digests. Bundle
artifact hashes are transitively bound by the validated bundle manifest; the
builder never assigns identity to an unvalidated directory traversal.

`ApplicationInputs` is reused as one canonical digest. Its existing repository
binding, normalized dependency pins and resource path/size/hash records remain
intact. Resource bytes are captured once during preparation. The exact build
closure is a separate sorted tuple of the existing `LockedDistribution` values
(name, version, archive SHA-256), produced by the existing lock reader and wheel
inspection. Declaration order and lock comments do not change that semantic
closure; accepted package versions or wheel bytes do. No resolver is added to
analysis or generation.

## Durable source provenance

`PreparedExposure` captures provenance while `GitSnapshot` is live and validated.
The generated `apizr-bundle-provenance.json` artifact records:

```json
{
  "kind": "git",
  "repository": "https://example.com/team/service.git",
  "requested_ref": "main",
  "resolved_commit": "1111111111111111111111111111111111111111",
  "subdir": "service",
  "repository_digest": {"algorithm": "sha256", "value": "..."}
}
```

This source object is nested under `source`; the artifact also records its schema
and core generator distribution version. The repository uses the existing
credential-free HTTPS/SSH validation. A branch name remains the requested ref;
the acquired commit is the durable Git revision. No checkout root, absolute
resource path, CA file, known-hosts file, SSH socket or credentials are recorded.

Local compiler sources use `kind: local` and the deterministic repository digest,
with no invented revision. Historical bundles without provenance, and low-level
rendering from evidence without a live acquisition identity, use
`kind: unrecorded`. Their repository evidence remains valid; no Git or local
acquisition history is invented. New bundle manifests optionally bind provenance
with `provenance_digest` and the existing artifact map.

Moving a workspace or copying a bundle preserves identity. Git and local
acquisitions of equal bytes intentionally differ in acquisition provenance.
Undeclared non-source data does not enter application resource identity.

## Planned and observed records

The builder snapshots and validates the bundle and wheels, constructs the plan,
and adds canonical `apizr-delivery-plan.json` to the build context. Those bytes
participate in `inputs_sha256` and are copied into the image. Its digest is set
before build using `sh.outerspace.apizr.delivery-plan-sha256`; the existing
`sh.outerspace.apizr.inputs-sha256` label remains required. Local inspection
checks both labels, immutable image ID, platform and non-root user.

`BuildResult` adds `delivery_plan`, `delivery_manifest` and
`delivery_manifest_digest`, all present together for a new build. The manifest
contains only its schema, `delivery_plan_digest`, `inputs_sha256`, `platform` and
`image_id`. Model validation checks all links and observed values.

Pass the build result's complete `delivery_manifest` into `PushRequest`.
Publication verifies its image/platform/inputs and the local plan label before
remote observation. A newly labeled image cannot be pushed through the historical
request path by omitting its manifest. `PushResult` includes both lineage digests,
while its existing remote configuration/manifest checks remain in force.

Installed core and OCI distribution versions come from distribution metadata;
the generator version comes from the bundle. These are version declarations,
not proofs of binary provenance. Docker/Buildx executable paths are operational
inputs, not binary identities. Attest's already verified version and binary
SHA-256 are retained in `DeliveryResult.attest_tool` after native verification.
Operator grants, authentication configuration, keys, trust paths and destinations
stay outside the portable plan and manifest. No additional authorization-scope
identity is introduced.

## Proof compatibility and limits

The existing `delivery/manifest.json` keeps `apizr.oci-delivery/v1` and its existing
scope. New proofs additionally bind canonical
`delivery/apizr-delivery-manifest.json` through that proof-binding manifest and
the native signed, timestamped receipt. Offline verification checks plan,
build, push, manifest and OCI reference consistency, then performs native
signature, timestamp and receipt recomputation against independent public trust.

Historical build/push v1 documents can omit all new lineage fields. Historical
six-file proof verification and OCI proof retrieval remain supported. New proofs
use exactly seven allowlisted public files. A historical proof cannot acquire a
transversal file without the corresponding build and push lineage. Published
0.4.0rc1 evidence is never rewritten.

Offline verification authenticates the recorded observations and their linkage.
It does not rerun source analysis, reconstruct the build context, re-execute the
build, inspect an image without Docker or contact the registry. `inputs_sha256`
is not recomputed from the receipt. This is delivery evidence, not SLSA provenance
or a claim of build supervision. Signing and publication remain separate actions;
mandatory-proof gating and multiple destinations are future increments.

## Qualification and schemas

The existing installed-package registry qualification uses the portable
application fixture (`six==1.17.0`, `data/message.txt`) acquired from a real Git
`main` ref. It distinguishes that ref from the resolved commit, removes source
and generated bundles, runs REST and MCP without source mounts, pushes immutable
images and signs/verifies both proofs offline after deleting the private key.
Substitutions cover source/repository, selection, resources, dependency pins,
artifacts, lock/wheels, plan label, build, push and the proof's manifest. Existing
historical proof and operator refusal qualifications remain enabled.

- [Bundle provenance schema](../specs/apizr-bundle-provenance-v1.schema.json)
- [Delivery plan schema](../specs/apizr-delivery-plan-v1.schema.json)
- [Delivery manifest schema](../specs/apizr-delivery-manifest-v1.schema.json)
- [OCI build and push](../reference/oci-service-plugin.md)
- [Attest delivery verification](../reference/attest-delivery-plugin.md)
