# Publish, discover and fetch delivery proofs

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel) and record its source commit.

After [signing a delivery proof](attest-delivery-plugin.md), the optional
`apizr-attest` plugin can store its existing six public files alongside the
image. It does not rebuild, retag, re-sign or timestamp anything. The image and
proof have different manifest digests. No private key or TSA is needed.

## Explicit tools and credentials

Prepare **ORAS 1.3.4** independently from its
[official release](https://github.com/oras-project/oras/releases/tag/v1.3.4).
Review the archive hash, extract it, then supply the absolute executable path
and **executable** SHA-256. Invocation snapshots and checks that executable and
its version; it never installs tools. Continuum Attest **0.1.0** and independent
trust use the same pins and setup as the signing page. Discovery needs only ORAS.

| Platform | ORAS archive SHA-256 | ORAS executable SHA-256 |
| --- | --- | --- |
| Linux amd64 | `f27adb935022d94df8dc77719c322dda592c78a0d57a6f7dcdd8d900b248c454` | `246c47e91bf2749a555ffe00a9824844c6df3a26d61974e3ce08f2077d79c556` |
| macOS arm64 | `217761a9500242ff473de8656b5aca21136ff39e17e9e61fd8936bbfd902704c` | `50ae33461ea6e2746b774587d2cb060850961ce01bfd6e70b48d4267919b491c` |

Supply a private registry configuration with exactly one `auths` entry, matching
the registry (including its port). Credential helpers, implicit Docker
configuration and inherited authentication variables are not used. `ca_file` is
optional for publicly trusted TLS. There is no insecure transport option.
A hash identifies reviewed tool bytes; it does not establish publisher trust.

The following complete Linux examples use illustrative image/artifact digests
and a signer. Replace those identities independently, paths and credentials
with your actual values. Install and enable the plugin as on the signing page.
The consumer only needs registry pull permissions, no Docker daemon or image.
If following the signing page's custom installation directory, append
`--plugins-dir "$work/plugins"` to each command below; otherwise they use the
default plugin store. Run the Python example in the separate environment where
`apizr-attest` is installed, not in the minimal core environment.

## Publish an existing proof

`publish.json`:

```json
{
  "schema": "apizr.publish-proof/v1",
  "proof_dir": "/work/proofs/delivery",
  "expected_reference": "registry.example:5443/services/rest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_signer": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "trust_store": "/private/independent-trust",
  "tool": {
    "executable": "/opt/attest/attest",
    "version": "0.1.0",
    "sha256": "c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35"
  },
  "transport": {
    "tool": {
      "executable": "/opt/oras/oras",
      "version": "1.3.4",
      "sha256": "246c47e91bf2749a555ffe00a9824844c6df3a26d61974e3ce08f2077d79c556"
    },
    "authentication": {
      "config_file": "/private/registry-auth.json",
      "ca_file": "/private/registry-ca.pem"
    }
  },
  "timeout_ms": 300000
}
```

```sh
apizr plugins run apizr-attest publish --arguments publish.json --timeout-ms 360000
```

The plugin snapshots the allowlisted files, runs all five native verification
checks without warnings or skips, reads the image manifest by digest, and calls
ORAS attach on those same private bytes. It rereads the artifact manifest by
digest, validates its subject and file descriptors, and requires discovery via
referrers before returning `receipt_published:true`.

The result schema is `apizr.published-proof/v1`. Keep `artifact_reference` for
fetch. `image_digest` identifies the image manifest;
`artifact_manifest_digest` identifies the proof manifest; `receipt_sha256`
identifies the unchanged native receipt bytes. The nested `verification` retains
the existing offline verification contract, whose `receipt_published:false`
means that verification itself performs no publication.

Publishing identical bytes is idempotent. Different signed receipts remain
separate artifacts. No proof is deleted. Failure after an attempted attach is
a result with `state:"remote_state_unconfirmed"`, `receipt_published:false`
and null artifact identities: the registry may retain the artifact even though
confirmation failed. This structured state reaches both Python and CLI callers;
a returned result alone is not a publication confirmation. A successful
confirmation has `state:"verified"`. A forced interruption cannot return a
result and must never be interpreted as rollback.
Discover and fetch an explicit digest to establish what is present.

## Discover candidates

`discover.json`:

```json
{
  "schema": "apizr.discover-proofs/v1",
  "expected_reference": "registry.example:5443/services/rest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "transport": {
    "tool": {
      "executable": "/opt/oras/oras",
      "version": "1.3.4",
      "sha256": "246c47e91bf2749a555ffe00a9824844c6df3a26d61974e3ce08f2077d79c556"
    },
    "authentication": {
      "config_file": "/private/registry-read-auth.json",
      "ca_file": "/private/registry-ca.pem"
    },
    "max_candidates": 128,
    "max_discovery_bytes": 1048576
  },
  "timeout_ms": 120000
}
```

```sh
apizr plugins run apizr-attest discover --arguments discover.json --timeout-ms 180000
```

`apizr.discovered-proofs/v1` contains digest-sorted `candidates`, each with a
reference, digest, advertised media type/size, artifact type and `verified:false`.
It never selects a candidate. Registry annotations do not establish trust.
`complete:true` means ORAS completed its direct referrer enumeration, not that
all proofs are valid or that the registry could not change afterwards.
An empty successful list differs from an authentication, network or API failure.

## Fetch the explicitly chosen digest

`fetch.json`:

```json
{
  "schema": "apizr.fetch-proof/v1",
  "artifact_reference": "registry.example:5443/services/rest@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "expected_reference": "registry.example:5443/services/rest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_signer": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "trust_store": "/private/independent-trust",
  "output_dir": "/received/delivery",
  "tool": {
    "executable": "/opt/attest/attest",
    "version": "0.1.0",
    "sha256": "c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35"
  },
  "transport": {
    "tool": {
      "executable": "/opt/oras/oras",
      "version": "1.3.4",
      "sha256": "246c47e91bf2749a555ffe00a9824844c6df3a26d61974e3ce08f2077d79c556"
    },
    "authentication": {
      "config_file": "/private/registry-read-auth.json",
      "ca_file": "/private/registry-ca.pem"
    }
  },
  "timeout_ms": 300000
}
```

```sh
apizr plugins run apizr-attest fetch --arguments fetch.json --timeout-ms 360000
```

Fetch validates the raw manifest hash and exact profile before receiving blobs.
Each individual blob is limited while reading, then checked against its advertised
size and hash. Local paths come from the code allowlist, never untrusted paths or
archive extraction. The existing native verifier requires the independently
chosen image, signer and trust. Only a fully verified proof becomes visible via
the existing locked atomic export. The destination must not exist; prepare its
parent as a user-owned directory without group/world write permission.

The result is `apizr.fetched-proof/v1`, with the same three identities and native
verification details. Afterwards use the signing page's `verify.json`, pointing
`proof_dir` at `/received/delivery`. Offline verify needs no ORAS, registry
credentials, private key, network, Docker daemon or local image.

Python callers use the same supervised operations:

```python
import json
from pathlib import Path
from apizr_attest import FetchRequest, fetch

request = FetchRequest.model_validate(json.loads(Path("fetch.json").read_text()))
result = fetch(request)  # optional cancel=threading.Event()
print(result.artifact_reference)
```

`publish(PublishRequest(...))` and `discover(DiscoverRequest(...))` follow the
same pattern. The plugin remains optional and separately installed.

## OCI profile and operational limits

The application type `application/vnd.apizr.attest.delivery.v1` is an Apizr
profile, not a new OCI standard. It uses an OCI 1.1 image manifest with the exact
image descriptor as `subject`, empty OCI config, and six individual layers of
`application/vnd.apizr.attest.delivery.file.v1`, ordered by filename:
`attest.yaml`, `delivery/build.json`, `delivery/manifest.json`,
`delivery/oci-manifest.json`, `delivery/push.json`, `receipt.yaml`.
Each layer has only its allowlisted `org.opencontainers.image.title` annotation.
The fixed manifest creation annotation `1970-01-01T00:00:00Z` is a deterministic
normalization marker, **not the signing time**. The native receipt keeps its
original signature and timestamp.

Only SHA-256 digest references in the same repository, single image manifests,
and this exact profile are supported. Tags, indexes, alternate config, external
blob URLs, embedded file data, extra files and hostile paths are refused.
ORAS attach/discover explicitly require `v1.1-referrers-api`; there is no tag
fallback. These operations do not change image tags or manufacture executable
images. Registries must retain both subject and artifact data.

Proof files are individually limited to 1 MiB, manifests to 1 MiB, ORAS to
128 MiB, and discovery output to 1 MiB by default (maximum 4 MiB). At most 128
candidates are returned. Limits cause errors, never a truncated successful list.
ORAS 1.3.4 follows referrer pagination through oras-go 2.6.2; Apizr bounds its
captured output and total execution time. The native client's in-memory page
collection is not an Apizr per-page memory quota. Depth is one; no recursive
referrer traversal. ORAS's experimental JSON contract is pinned and tested,
including `reference`, descriptors and `referrers`; no nonexistent JSON schema
version is assumed.

Each operation has one total deadline (maximum 540 seconds); the outer CLI
runtime timeout must allow that operation to finish. Native output is bounded
while read. A fresh process group and private snapshots use the existing runtime
cleanup, including cancellation. Trusted native tools are not sandboxed;
detached descendants and uninterruptible kernel tasks retain the runtime's
limits. Local cleanup cannot undo a remote transfer. Native diagnostics and
credentials are never copied into results or artifacts.

Normative references and the pinned transport implementation:

- [OCI image manifest 1.1.1](https://github.com/opencontainers/image-spec/blob/v1.1.1/manifest.md)
- [OCI distribution 1.1.1 referrers](https://github.com/opencontainers/distribution-spec/blob/v1.1.1/spec.md#listing-referrers)
- [ORAS attach](https://oras.land/docs/commands/oras_attach/) and [discover](https://oras.land/docs/commands/oras_discover/)
- [Pinned ORAS 1.3.4](https://github.com/oras-project/oras/tree/v1.3.4) and [oras-go 2.6.2 pagination](https://github.com/oras-project/oras-go/blob/v2.6.2/registry/remote/repository.go)

## Reproduce the installed-package proof

```sh
uv run --locked pytest tests/attest_plugin --cov=apizr_attest
uv run --locked pytest tests/oci_plugin --cov=apizr_oci
python3 scripts/smoke_oci_registry.py --artifacts --output /private/test-results/artifacts
```

The fixture extends the existing build/push/sign tests with a real authenticated
HTTPS Zot 2.1.21 registry, local TSA and pinned ORAS. It installs wheels
outside the checkout, publishes two proofs, checks idempotence and direct ORAS
interoperability, then deletes original proofs and private signing keys. A
separate consumer has no Docker socket and a registry identity restricted to
read access by Zot policies, also enforced by its HTTPS test gateway. It fetches the selected digest, compares all six files, and verifies in
a final networkless container with ORAS and registry credentials removed.
The core's files/distributions are compared before and after. Public results and
refusals are retained by CI. This fixture does not qualify Docker Hub or Trunx.
Apizr release attestation, its secrets and the continuum-attest repository are
unchanged.
