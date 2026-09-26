# Sign and verify an OCI delivery receipt

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel) and record its source commit.

`apizr-attest` is an optional, separately installed extension. It binds a verified
OCI delivery to a user-selected Continuum Attest identity and RFC 3161 authority.
Its scope is **verified OCI delivery; build not supervised by Attest**. The
`attest` and `verify` operations do not rebuild an image, certify SLSA, prove
reproducibility, or upload the receipt. The plugin also provides explicit
`publish`, `discover` and `fetch` operations.
Use the separate [publish, discover and fetch operations](attest-oci-artifacts.md)
to transport an existing verified proof through an OCI registry.

## Install explicitly

First complete the [OCI build and push example](oci-service-plugin.md). Keep the
versioned `result` objects from both extension responses as `build-result.json`
and `push-result.json` (not the enclosing extension protocol envelopes).
Keep the immutable local image available until attestation finishes.

Prepare a separate wheelhouse containing the core, both plugin wheels and their
reviewed transitive Python dependencies. Only preparation accesses an index:

```sh
work=$(mktemp -d)
uv build --wheel --out-dir "$work/wheels"
uv build --wheel plugins/oci --out-dir "$work/wheels"
uv build --wheel plugins/attest --out-dir "$work/wheels"
cd "$work"
uv venv --seed --python 3.14 prepare
prepare/bin/python -m pip download --only-binary=:all: --dest wheels \
  wheels/outerspace_apizr-0.3.0-py3-none-any.whl \
  wheels/apizr_oci-0.0.0-py3-none-any.whl \
  wheels/apizr_attest-0.0.0-py3-none-any.whl
uv venv --python 3.14 core
uv pip install --python core/bin/python --offline --no-index --find-links wheels \
  wheels/outerspace_apizr-0.3.0-py3-none-any.whl
```

Use the complete `lock_wheels.py` example on the linked OCI page to create a
reviewed lock for this wheelhouse. All plugin dependencies go into the plugin's
own environment; the core stays minimal. No additional mandatory core dependency
is introduced. The plugin versions remain `0.0.0`, built locally, not released.

```sh
prepare/bin/python lock_wheels.py wheels attest.lock
sha=$(prepare/bin/python -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("wheels/apizr_attest-0.0.0-py3-none-any.whl").read_bytes()).hexdigest())')
core/bin/apizr plugins install wheels/apizr_attest-0.0.0-py3-none-any.whl \
  --sha256 "$sha" --requirements attest.lock --wheelhouse wheels \
  --plugins-dir "$work/plugins"
core/bin/apizr plugins enable apizr-attest --version 0.0.0 --plugins-dir "$work/plugins"
```

## Explicit binary, identity and trust

Provision **Continuum Attest 0.1.0** from
[Alien6-Studio/continuum-attest](https://github.com/Alien6-Studio/continuum-attest/releases/tag/v0.1.0)
independently. Review the release archive checksum before extraction. Invocation
requires an absolute executable path, version `0.1.0`, and the SHA-256 of the
**extracted executable**, not the archive. The plugin copies bounded verified
bytes into its private workspace and checks `attest --version` before use.
It never downloads, compiles Rust, or installs a tool during an operation.

The existing Apizr pin identifies these official archives/executables:

| Platform | Archive SHA-256 | Executable SHA-256 |
| --- | --- | --- |
| Linux x86_64 | `f51201745b30be356e066cd615a7ef41fed92b17cf720ceb03e7f2a4d58505ad` | `c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35` |
| macOS arm64 | `93d02f9fc90a8c0dd6c8f3df05ce56660b89b83eb334a02aaad4c3f68f9ceb4d` | `fa572bbc2c00f55f37be15564661c693d801fd58f6b9b938924698a986bab705` |

Use your own previously prepared Attest key, its key ID, and its raw 32-byte
public key as 64 lowercase hex characters (`expected_signer`). The private file
uses Attest's PKCS#8 PEM convention. Key generation is never implicit. Do not use
the Apizr release signing identity.

Supply an independent native Attest trust directory containing `<key-id>.pub`,
`trust.toml`, and `tsa/*.crt` (pinned issuing certificates). No trust is copied
from the delivered proof. Attest performs the cryptographic, revocation and
RFC 3161 checks; this plugin introduces no signature or receipt format.
Any warning, including acceptance of a receipt predating key revocation, is a
refusal in this strict profile. The trust directory cannot reside in the proof.

The TSA URL must be chosen explicitly; there is no default public service.
Attest 0.1.0 supports HTTP and HTTPS RFC 3161 endpoints; HTTPS keeps its TLS
validation. Timestamp authenticity depends on the independently pinned issuing
certificate. Credentials, query tokens and fragments in the URL are refused.
No proxy or parent authentication environment is inherited.

## Attest a published delivery

Example `attest.json` (replace the illustrative identities with your actual
build/push results, paths, signer and TSA):

```json
{
  "schema": "apizr.attest-delivery/v1",
  "build_result": "/work/build-result.json",
  "push_result": "/work/push-result.json",
  "expected_reference": "registry.example:5443/services/rest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_signer": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "docker": {
    "executable": "/usr/bin/docker",
    "socket": "/var/run/docker.sock"
  },
  "authentication": {
    "config_file": "/private/registry-auth.json",
    "ca_file": "/private/registry-ca.pem"
  },
  "tool": {
    "executable": "/opt/attest/attest",
    "version": "0.1.0",
    "sha256": "c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35"
  },
  "key_file": "/private/attest/cccccccccccccccccccccccccccccccc.key",
  "key_id": "cccccccccccccccccccccccccccccccc",
  "tsa_url": "https://tsa.example/timestamp",
  "trust_store": "/private/independent-trust",
  "output_dir": "/work/proofs/delivery",
  "timeout_ms": 300000,
  "max_output_bytes": 1048576
}
```

`registry-auth.json` has the same explicit single-registry `auths` format as
push; it is never exported. Docker socket/daemon trust requirements remain those
of the OCI plugin. `ca_file` is optional for publicly trusted registry TLS.
Prepare the output's parent as a user-owned directory without group/world write
permission. The destination must not exist.

```sh
core/bin/apizr plugins run apizr-attest attest --arguments attest.json \
  --plugins-dir "$work/plugins" --timeout-ms 360000
```

The plugin validates both schemas and their image/platform/input identities,
requires `published:true` from push, and reuses OCI's read-only observation API.
It inspects the immutable local ID and the remote **digest reference**, not the
tag. Moving a published tag does not change the image being attested. The exact
remote manifest bytes are retained and their SHA-256 is checked, without JSON
reserialization. `inputs_sha256` is a build declaration corroborated by the local
image label; the receipt does not reconstruct or re-hash the original inputs.
No Git commit or build history is invented.

A fixed generated pipeline runs only `true`, declaring `delivery/` as inputs and
outputs. No supplied pipeline or business command is executed. The real command
is `attest run --pipeline attest.yaml --sign --timestamp --key ID --tsa URL`.
The private key copy is mode 0600 in the runtime's private workspace and removed
on completion or failure; runtime cleanup also covers interruption. The original
key is never changed. The fresh receipt must pass offline verification before
an atomic, cooperating-writer-locked export becomes visible.

## Verify after transport, without Docker or a private key

Copy the proof elsewhere and supply the expected reference and signer from an
independent source. Do not infer them solely from the proof's contents.
Example `verify.json`:

```json
{
  "schema": "apizr.verify-delivery/v1",
  "proof_dir": "/received/delivery",
  "expected_reference": "registry.example:5443/services/rest@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "expected_signer": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "trust_store": "/private/independent-trust",
  "tool": {
    "executable": "/opt/attest/attest",
    "version": "0.1.0",
    "sha256": "c73ecb92a2ebbf324cb0bdcf631fc3505f3395aa1acad30501284156cef9ce35"
  },
  "timeout_ms": 120000
}
```

```sh
core/bin/apizr plugins run apizr-attest verify --arguments verify.json \
  --plugins-dir "$work/plugins" --timeout-ms 180000
```

Each call runs `attest verify receipt.yaml --recompute --workspace DIR
--trust-store TRUST --offline --format json` on a private snapshot of the proof.
It never executes the pipeline, accesses Docker, or consults old verification
results. It requires the expected signer, no warnings, and exactly one passing
check each for `schema`, `consistency`, `signature`, `timestamp`, and `recompute`.
A zero exit, global pass, missing or skipped check is insufficient. It also
checks the expected reference, raw OCI bytes and deterministic delivery manifest.
A receipt for another image is refused. `--trust-receipt-timestamp` is never used.

Both operations return `apizr.attest-delivery-result/v1`, with `reference`,
`manifest_digest`, `signer`, `receipt_sha256`, five checks, and explicit scope.
`receipt_published:false` means no receipt was stored in a registry.
`registry_availability_verified:false` makes clear that offline verification
does not establish current registry availability.

The portable allowlist is `receipt.yaml`, `attest.yaml`, and four files in
`delivery/`: validated build and push results, `oci-manifest.json` (raw), and
`manifest.json`. There are no required absolute signing-machine paths, secrets,
keys, Docker configuration, trust store or cache. The fixed pipeline is checked
before recomputation. Each proof file is bounded to 1 MiB; trust to 128 files and
4 MiB; private key to 16 KiB; binary to 128 MiB. Special files and symlinks in
snapshotted paths are refused. Native stdout/stderr share the configured read
budget; the total extension timeout also bounds acquisition and signing.

## Python API and boundaries

Install the optional package in a separate application environment, then:

```python
import json
from pathlib import Path
from apizr_attest import VerifyRequest, verify

request = VerifyRequest.model_validate(json.loads(Path("verify.json").read_text()))
result = verify(request)  # optional cancel=threading.Event()
print(result.model_dump(by_alias=True))
```

`attest(AttestRequest(...))` follows the same pattern. Both APIs use the existing
extension runtime, a fresh process group, empty parent environment and bounded
protocol. The selected binaries and plugins remain trusted user code, **not a
sandbox**. Ordinary descendants are cleaned by the runtime; detached descendants
and uninterruptible kernel tasks retain its documented limits. A forced stop
immediately after export can leave a fully validated proof; inspect it rather
than assuming rollback. Cooperating exports never overwrite an existing proof.

## Reproduce the integration proof

```sh
uv run --locked pytest tests/attest_plugin --cov=apizr_attest
uv run --locked pytest tests/oci_plugin
python3 scripts/smoke_oci_registry.py --attest --output /private/test-results/attest
```

The last command requires a Docker host supporting privileged disposable Linux
containers. It reuses the authenticated HTTPS registry and two Docker daemons
from the push proof, prepares the pinned x86_64 Attest binary, and uses a local
OpenSSL RFC 3161 authority and dedicated test key. Wheels are installed outside
the checkout. It signs a real published image, copies the proof, deletes the
original and private key, and verifies under `unshare --net` with independent
trust. Negative cases and tool identities are retained as artifacts. No machine
trust store or Apizr release workflow, secret or identity is changed.
