---
title: Connect Apizr to your deployment platform
description: Share service descriptions and delivery results with your deployment platform. Learn how Apizr works alongside tools such as Trunx.
---

# Connect Apizr to your deployment platform {#external-governance-handoff}

Use Apizr's exports to tell your deployment platform what a service does and
which container contains it. Your platform decides who can deploy and use it.
Apizr also works on its own, locally.

[Trunx](https://trunx.io/), a private registry for software packages and container
images, uses Apizr 0.4.4 to publish REST and MCP services and manage their delivery
approvals.

A successful Apizr delivery check confirms technical conditions. It does **not**
replace your organization's deployment approval or access controls.

## Existing documents, one identity graph

No `CapabilityRelease` schema is introduced. The exported files are byte-for-byte
copies of the existing direct REST/MCP bundle's public JSON records. They include
no Python modules, application resources, wheels, credentials or operator grants.
Docstrings, declared expressions and source metadata remain public document
content; review them before sharing.

| Need | Existing document / location |
| --- | --- |
| Stable logical capability ID | `capability-catalog.json`: `capabilities[].id`, `python:<module>:<symbol>` |
| Description, declared input/output and uncertainty | Catalog `sources[].inspection.capability_ir.capabilities[]`; `repository-interface.json` invocation contracts |
| Concrete generated REST routes or MCP tools | `apizr-repository-rest.json` / `apizr-repository-mcp.json`, `openapi.json` / `mcp-tools.json` |
| Static eligibility, constraints and limits | `repository-readiness.json` assessments and embedded policy; catalog inspections; `capability-graph.json` |
| Selected capabilities and execution contracts | `exposure-policy.json`, `exposure-plan.json` |
| Analysis policies | Catalog `scan_policy`, graph `graph_policy`, readiness `policy`, each with its digest |
| Source acquisition and generator | `apizr-bundle-provenance.json` when present; unrecorded provenance remains unrecorded |
| Bundle and file identities | Existing bundle manifest `artifacts`, source hashes and `repository_interface_digest` |
| Exact build and delivery linkage | BuildResult's `delivery_plan.bundle_manifest_digest`, `delivery_manifest` and `delivery_manifest_digest` |
| Immutable image, proof and delivery observations | Existing PushResult, PublishResult and AdmissionResult, retained separately |

A logical ID survives a function-body, docstring or annotation change. It is not
a version, artifact digest or globally unique organization ID. Keep the source
repository/provenance and bundle digest alongside it; two projects can legitimately
use the same `python:pricing:total`. Renaming a module/symbol changes the ID. Source
bytes, contracts, policies, selected exposure and generator/build inputs have
separate content identities. A changed body can keep the same input/output
contract while changing source, catalog, bundle and downstream delivery identities.

Declarations (annotations, docstrings, policy choices) are not runtime facts.
Graph/readiness results are static analysis with explicit unknowns and limits;
`unknown` never means safe. Generated endpoints/tools describe the generated
interface, not a running or reachable deployment. Only executed calls and delivery
observations are runtime evidence, with the scope and time of their observation.

## Export and verify in CI

Start with the existing `apizr ci build-rest` / `build-mcp` or `apizr expose build`
commands and explicit analysis authority. Build the OCI image through the existing
OCI plugin when an image is needed. Preserve the original plugin results.
`apizr plugins run` returns an envelope: save its `result` object as `build.json`.
The Python API already returns the corresponding typed BuildResult.

```sh
apizr expose export --bundle-dir ./rest-bundle --interface rest \
  --output-dir ./capability-documents --build-result ./build.json \
  > ./bundle-manifest.json
```

Omit `--build-result` for a standalone local bundle. When supplied, every existing
plan link is checked against the documents and the observed build's lineage is
validated. Historical builds without delivery lineage still work through their
original APIs, but cannot establish this extra bundle-to-build link.

Transport `capability-documents/`, `build.json`, the original push/publication/
admission results and the selected remote proof through your governance system's
**documented, separately authenticated ingestion mechanism**. Apizr does not
invent a Trunx API. Keep the independently approved image reference, proof
reference and bundle digest in the pipeline's protected inputs.

After receiving documents, a consumer can validate them without business code:

```sh
apizr expose verify --evidence-dir ./received-documents --interface rest \
  --bundle-sha256 "$REVIEWED_BUNDLE_SHA256" --build-result ./build.json \
  > ./verified-bundle-manifest.json
```

Both new commands emit the **existing bundle manifest JSON only** on stdout,
return `0` on success and `2` with `apizr expose: evidence_invalid` on stderr on
invalid/inaccessible evidence. Argument errors also return `2`. Export validates
the complete bundle without importing it, refuses nonempty output, and publishes
atomically. Verify reads only fixed-name regular JSON files, refuses links,
ambiguous duplicate keys and unknown schemas/fields, and caps selected evidence
at 64 MiB. Other files are ignored and cannot contribute evidence.

The Python equivalents are `export_evidence` and `verify_evidence` in
`apizr.repository_interfaces.evidence`; they return existing RestManifest or
MCPManifest models and raise input/integrity exceptions. The initial export
supports direct repository REST/MCP bundles used by the OCI service builder.
Governed execution bundle schemas remain supported by their existing runtime
validators, not this projection. No schema migration or weakening occurs.

Verification proves consistency with the **independently selected digest**. It
does not authenticate a hash supplied by an attacker, hash absent source/layer
bytes, import the application, rerun analysis from source, inspect a registry or
verify a signature. For delivery authenticity use the existing Attest `fetch`,
`verify` and `admit` operations with independently configured signer/trust.
A BuildResult alone is not a verified proof.

## Delivery, retries and consuming a precise artifact

Use `proof_requirement: required` before building when proof must gate promotion.
The current `apizr delivery run` / `resume` coordinator and plugin operations
remain the only delivery interfaces. Their JSON states and exit semantics are
specified in [multi-destination delivery](multi-destination-delivery.md).

| Observation | What the pipeline may conclude |
| --- | --- |
| Push `published:true`, `transfer_verified:true` | Image transferred and immutable remote identity checked |
| Required push `destination_promoted:false`, `delivery_admitted:false` | Destination promotion is withheld pending technical admission |
| Publish `state:verified` | Selected proof artifact is published and checked; no deployment approval |
| Admission `state:admitted` | Selected proof verified and destination observed at the expected digest |
| `remote_state_unconfirmed`, timeout, interruption or partial batch | Re-observe/resume exact identities; never infer rollback or success |
| External environment decision | Organizational authority, evaluated by the external system, not Apizr |

Admission re-fetches the explicitly selected proof, checks its exact image and
manifest, signature, timestamp and recomputation before promotion. A wrong or
altered proof is refused. An identical destination permits idempotent completion;
a conflicting image is refused. Tags can subsequently move; consume the recorded
`repository@sha256:...` reference, never infer a release from a tag alone.

A minimal final pipeline step, after the external decision has been authenticated
and matched to the exact environment/image/proof by your integration, is:

```sh
# REVIEWED_IMAGE_REFERENCE comes from that exact authorized decision.
# The integration must first compare it to the admitted image_reference.
docker pull "$REVIEWED_IMAGE_REFERENCE"
# Pass the same digest reference to your deployment system.
```

These are integration boundaries, not a simulated approval or Trunx request.
Do not derive authorization from a client-controlled `approved: true` JSON field.
See [admission](delivery-admission.md) for independent technical checks and races.

### First publication and ambiguous Docker diagnostics

For the exact destination-tag preflight only, 0.4.4 handles Docker's exact
`manifest unknown` / `manifest unknown: manifest unknown` diagnostics by checking
`https://<selected-registry>/v2/<selected-repository>/manifests/<selected-tag>`.
The fallback uses the already snapshotted explicit Basic auth and CA, verified
TLS, no redirects/proxies, a bounded child process and a 64 KiB response limit.
Only HTTP 404 with one unambiguous OCI `MANIFEST_UNKNOWN` error confirms absence.
A message alone, HTML 404, auth/TLS failure, redirect, timeout, wrong error code or
multiple errors fails closed. Bearer challenges are not followed by this fallback;
Docker's previously supported exact reference-bound absence remains supported.
This is a bounded compatibility path, not a general registry authentication client.
See the [OCI distribution specification](https://github.com/opencontainers/distribution-spec/blob/main/spec.md#pulling-manifests).

## Schema evolution and independent readers

Schema identifiers are versioned independently of package versions. Existing v1
JSON and canonical identities are unchanged; 0.4.4 emits no added fields into
these strict contracts. Breaking meanings require a new schema version. An
apparently additive field can break strict v1 readers and requires explicit
compatibility review. Reject unknown versions/fields; retain original bytes for
inspection, never silently discard fields or relabel a document as v1.

[Canonical serialization](../architecture/delivery-identities.md) is UTF-8 JSON,
lexicographically sorted keys, compact separators, explicit contract defaults/
nulls except model-defined omissions, no NaN and exactly one final LF. SHA-256
hashes those exact canonical bytes. Source digests hash original source bytes;
OCI digests hash original registry manifest/blob bytes. Do not reformat files
before checking artifact hashes. Optional `proof_requirement` omission retains
historical plan identities. The historical proof-binding serializer is unchanged.
JSON Schema validates structure; cross-document hashes and semantic validators
are additional required checks.

The existing [catalog](../specs/apizr-catalog-v1.schema.json),
[interface](../specs/apizr-repository-interface-v1.schema.json),
[plan](../specs/apizr-delivery-plan-v1.schema.json) and
[manifest](../specs/apizr-delivery-manifest-v1.schema.json) schemas are supplemented
by generated schemas for the unchanged
[build](../specs/apizr-oci-build-result-v1.schema.json),
[push](../specs/apizr-oci-push-result-v1.schema.json),
[proof verification](../specs/apizr-attest-delivery-result-v1.schema.json),
[proof publication](../specs/apizr-published-proof-v1.schema.json),
[admission](../specs/apizr-delivery-admission-v1.schema.json) and
[observation](../specs/apizr-delivery-observation-v1.schema.json) results.
Regenerate the latter with `scripts/export_delivery_schemas.py`.

## Deterministic A/B example and qualification boundaries

`examples/governance/a/pricing.py` and `b/pricing.py` define the same
`python:pricing:total(unit_cents: int, quantity: int) -> int`. A charges 100 cents
handling; B charges 150. For `(100, 2)` the executed results are 300 and 350.
The stable ID stays equal; source, catalog, exposure and bundle digests differ.
The contract remains compatible; its description records the changed fee.

Run from a clean installed environment, outside the checkout:

```sh
python -I /path/to/apizr/scripts/governance_evidence_proof.py \
  --examples /path/to/apizr/examples/governance --output ./governance-proof
```

The script retains both REST/MCP JSON exports and `comparison.json`, executes only
this trusted example, removes generated source, then verifies the documents.
It explicitly records `registry_executed:false` and `external_governance_executed:false`.
Coordinated target qualification runs it using the retained core wheel.

The separate real disposable HTTPS registry qualification exports documents from
actual REST/MCP builds, verifies them against their BuildResults after deleting
source/bundles, and exercises push, proof publication, immutable retrieval,
admission, tampering and resume with independently installed consumers. Its
registry/TSA are test services, not Trunx. Mocked unit tests are a third, separate
layer. See the [0.4.4 verification record](../contributing/verification.md#044-publication-record)
for qualification details.
