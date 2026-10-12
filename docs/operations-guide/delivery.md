# Build and deliver a service image

Package a reviewed direct bundle and hand an immutable image plus its actual
verification records to operations. A local build, registry transfer, proof and
organizational deployment decision remain separate stages.

## Before you begin

Use a working [quote service](../examples/business-quote.md). Install the `oci`
profile, or `delivery` for the optional Attest path, using
[Install Apizr](../getting-started/install.md#choose-a-plugin-profile).
Check Docker Engine/Buildx, an explicit local Unix socket and a trusted
digest-pinned Python base on `linux/amd64` or `linux/arm64`.

## Prepare exact image inputs

The [OCI reference](../reference/oci-service-plugin.md#prepare-server-dependency-locks)
shows how to download compatible **Linux target** wheels and create one reviewed
hash per exact pin. Include the generated transport closure and any declared
application pins. macOS wheels do not become Linux wheels. Preparation may use a
package index; the image build installs only retained wheels offline.

Review a grant for the exact installed plugin, base, platform, bundle, lock,
wheelhouse, Docker parameters and chosen local tag. It needs only `image.build`
and `registry.read`. Invoke `apizr plugins run outerspace-apizr-oci build` with
that operator policy and the complete arguments described in the reference.
Keep the extension envelope and its `result` separately.

## Check the local image

The build result has `published:false`, local `image_id`, `platform`,
`inputs_sha256`, `delivery_plan`, `delivery_manifest` and its digest. Check the
real service in a container through the example's request. Docker startup,
health checks and stopping that container are host procedures.
Killing the build client does not prove daemon work stopped; inspect only the
explicit test tag and retained observations before retrying.

## Transfer and verify

Push uses a separate narrowly scoped `registry.read` / `registry.publish` grant
for one repository. It consumes the exact build result without rebuilding.
A successful transfer reports the observed remote immutable identity; retain
that `repository@sha256:...` reference rather than assuming a tag stays fixed.
The [disposable delivery example](../examples/verified-delivery.md) provides a
complete local TLS/authenticated registry procedure without production secrets.

## Add Attest when the handoff needs proof

Provision the pinned Continuum Attest tool, a demonstration identity and an
independent trust directory. Signing requires `receipt.sign` and
`timestamp.request` separately from publication rights. Offline verification
requires public trust and the expected signer, not a private key.

The receipt verifies **verified OCI delivery; build not supervised by Attest**.
A valid receipt proves neither scientific quality nor general compliance.
The example tampers with a proof and requires actual verification to refuse it.
[Proof-required admission](../reference/delivery-admission.md) is an optional
technical destination gate; it is not organizational approval.

## Handle incomplete delivery and platform handoff

For explicitly configured multiple destinations, the supported
[delivery coordinator](../reference/multi-destination-delivery.md) retains per-target
observations and `resume` rechecks exact evidence. Remote state may remain
unconfirmed after interruption. There is no inferred rollback or remote deletion.

[Export existing capability documents](../reference/external-governance.md) and
retain build/push/proof results for Trunx or another platform's authenticated
ingestion mechanism. No new Trunx API is implied. After your platform's real
approval, consume the exact reviewed image reference with its deployment procedure.
