# Hand over a verifiable service image

Build scenario C's quote service, transfer it to a disposable local registry and
call the transferred image from an independent Docker daemon. Optionally create
and verify a real Attest receipt with a demonstration identity.

## Expected result and prerequisites

The quote returns the same **9,180 cents** through container REST and MCP after
the original project and bundles are removed. Evidence retains actual build,
transfer and immutable remote identities. With Attest enabled, native verification
accepts the original proof and refuses altered proof.

Use Python 3.11+, Git and Docker Engine/Buildx on a trusted Linux/macOS host.
Docker must support the fixture's privileged nested Linux daemons; these are
test infrastructure, not an untrusted-code sandbox. Preparation downloads public
Apizr core/OCI/Attest **0.4.5**, Linux target wheels and trusted tool/base images.
The optional native tool is Continuum Attest 0.1.0 with pinned archive/executable
hashes. No paid platform, production credential, organizational key or remote
publication is used.

Download [verified-delivery.zip](../downloads/verified-delivery.zip), extract it
outside the checkout and open `verified-delivery/`. It contains the scenario C
quote files plus the repository's real registry/proof qualification drivers and
their supporting fixtures. Product code is installed from PyPI, not this archive.
All example data is fictional and GPL-3.0-or-later.

## Run a build and local transfer

```sh
python run.py --output ../delivery-evidence
```

`run.py` creates a temporary fixture workspace, then runs the existing real
authenticated TLS registry with independent builder/consumer daemons. It installs
and activates the published OCI plugin into a separate store, generates the quote
bundle through the installed core, prepares exact server-wheel hashes and grants
only the documented build/push targets. Docker and OpenSSL create the registry
and demonstration credentials; those are host/test procedures, not Apizr commands.

The fixture invokes real `apizr plugins run ... build` and `push`, exports the
bundle evidence, deletes source/bundles, then makes real container REST/MCP calls.
It checks authorization refusals, altered build inputs and interrupted transfer
without treating an uncertain remote state as success.

## Check the retained result

```sh
python - <<'PY'
import json
from pathlib import Path
root = Path('../delivery-evidence')
builds = json.loads((root / 'results.json').read_text())
pushes = json.loads((root / 'push-results.json').read_text())
calls = json.loads((root / 'application-delivery-proof.json').read_text())
assert len(builds) == len(pushes) == 2
assert all(b['result']['published'] is False for b in builds)
assert all(p['published'] and p['transfer_verified'] for p in pushes)
assert calls['source_removed'] and calls['bundles_removed'] and not calls['source_mounts']
assert calls['rest_result']['total_cents'] == 9180
assert calls['mcp_result'] == calls['rest_result']
print('Built, transferred, and called the quote through REST and MCP')
PY
```

`image_id` identifies the local engine image; a remote manifest digest is separate.
`build-response.result` is not the whole extension envelope. Keep both plus
`delivery_plan`, `delivery_manifest` and exported document hashes for review.
Do not substitute a successful build for a verified transfer.

## Optional Attest identity and tampered-proof refusal

Choose a new evidence directory:

```sh
python run.py --attest --output ../attest-evidence
```

The fixture generates a disposable private key, configures public signer trust
independently, and runs a local RFC 3161 test authority. Exact signer/key/TSA
grants are distinct from registry publication rights. Native Attest checks the
receipt with that independent trust; altered manifest/signature/timestamp cases
must refuse. `attest-results.json` and `attest-refusals.json` retain verified
outcomes. Test private keys/authentication remain in disposable infrastructure;
they are not exported as public proof.

The scope is **verified OCI delivery; build not supervised by Attest**. This proves
neither scientific quality nor organizational approval. For proof transport and
destination admission, see [the exact optional contracts](../reference/attest-oci-artifacts.md).

## Limits, failures and cleanup

If Docker, nested daemon startup, base/tool acquisition, native Attest or a
verification check is unavailable, this scenario is **not verified**. Inspect
`proof.log` privately, correct the prerequisite and retry into a new output path.
No assertion is replaced by a fake response. Preparation/build duration depends
on the host and downloaded images; no fabricated performance target is claimed.

The fixture's `finally` cleanup removes its named containers, network, volume and
fixture image. It never globally prunes Docker or deletes unrelated images.
Evidence directories remain for your review; remove only those you created when
finished. Returning to a known service image uses your host/platform procedure,
not a native Apizr rollback command. Trunx handoff uses
[existing exported records](../reference/external-governance.md), not an invented API.
