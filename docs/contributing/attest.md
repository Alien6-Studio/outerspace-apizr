# Apizr's managed release identity

Apizr uses a dedicated Ed25519 key for delivery receipts. This identity is
separate from continuum-attest's own signing keys and from GitHub's keyless build
provenance. The repository maintainer manages its provisioning and revocation.

- Key identifier: `ac3b0b1c565ef9e18f894c10f5ce1cdb`.
- Raw public key: `1d397e601c7efc4b8e372efa3d23bfbd819ecc02070d38a80335b1fd9a4e72e1`.
- Public key and trust policy: `.attest/trust/` in the protected repository.
- Private-key storage: `APIZR_ATTEST_SIGNING_KEY`, a PKCS#8 PEM provisioned on
  2026-09-21 in the protected `pypi` GitHub environment with maintainer
  authorization. The temporary local private copy was removed after verification.
  No repository-wide secret or private key in source control.
- Timestamp authority: DigiCert's documented
  [RFC 3161 service](https://knowledge.digicert.com/general-information/rfc3161-compliant-time-stamp-authority-server),
  `http://timestamp.digicert.com`. Only the signature's digest is submitted.
- Pinned issuer: **DigiCert Trusted G4 TimeStamping RSA4096 SHA256 2025 CA1**,
  DER SHA-256 `ca0b1554ecd901ea19dcad8749e9f2648c8d6dfcea1add9d2c2109415bb82ccd`.
  Its certificate was obtained from DigiCert's `cacerts.digicert.com` service.
  Verification requires the pinned issuer and validates the token signature,
  message imprint, certificate purpose and validity at the timestamped time.

The identity setup proof under `tests/fixtures/attest-identity/` is an explicitly
labeled test message, not a release receipt. CI verifies its signature and real
RFC 3161 token offline, then requires rejection of changed content, a missing
timestamp, an invalid signature and an untrusted key. PRs never use the private
release key or call the timestamp service.

An authorized local test also signed and timestamped the actual artifacts from
[CI run 35624060995](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/35624060995)
at `d254da33f649b853dee8bfa5669f0ca383e6f282`. GitHub provenance for the wheel,
sdist and CI archive was verified against the repository, workflow, commit and
`master` ref before signing. All five Attest checks passed again after extracting
the receipt archive, using the independently held repository trust store; every
archived file matched the verified input's SHA-256. The test receipt archive has
SHA-256 `76ad8ebc0c69991c689759521c6e99123544db5d1798124af7ae30956f1e2626`.

These were post-release CI verification builds declaring 0.2.0, not the immutable
published 0.2.0 distributions. This local test does not establish execution of
the protected GitHub publication job or delivery of a new release. The existing
environment protections remain: required maintainer review, `v*` tags only and
no administrator bypass.

## Receipt before publication

The publication workflow first verifies the exact CI distributions and their
GitHub provenance. A separate environment-protected job then installs the
hash-pinned Attest 0.1.0 binary and signs a fresh delivery pipeline. It declares
the wheel, sdist, CI/dependency evidence and a SHA-256 manifest with the source
commit and CI run identifier as inputs and outputs. It does not rebuild them or
claim that Attest supervised their original build. GitHub provenance remains
the build evidence.

The private key is available only to the signing step. The script removes it
from the child environment, writes it with mode 0600, and deletes the temporary
file on success or failure. An always-run cleanup step covers interruptions.
Only an explicit public set enters the resulting archive; keys and caches are
excluded. The PyPI publisher still executes no checkout or repository code.

Publication requires the expected Apizr signer and **all five** verification
checks to pass: schema, consistency, signature, timestamp and recomputed hashes.
Missing or skipped checks, warnings and timestamp-service failures block; there
is no unsigned fallback. The environment's existing reviewer and tag restrictions
remain in place. The workflow has not yet published a release with this receipt;
the final delivered-artifact criterion in #73 remains open until it does.

## Verify a delivered receipt

Use the pinned Attest version and download `apizr-attest-receipt.tar.gz` from the
release. Extract it into a new directory. The archive includes the signed
pipeline, receipt, manifest and exact files; it duplicates the delivered wheel
and sdist so hash recomputation needs no network.

Obtain the trusted public key/policy and TSA issuer **independently**, for example
from a previously reviewed repository revision. Do not establish trust solely
from the archive's own `trust/` directory. With the extracted directory as the
current directory:

```sh
attest verify receipt.yaml --recompute --workspace . \
  --trust-store /path/to/independently-trusted-apizr-keys --offline --format json
```

Require `signed_by` to equal the public key above and each of the five named
checks to be `pass`, with no warnings. A top-level `pass` alone is insufficient:
Attest permits optional checks to be skipped, whereas Apizr's publication gate
does not. Compare the archived distribution SHA-256 values with the files
downloaded directly from PyPI/the release. For automated enforcement, the
repository's `scripts/attest_release.py` contains the same strict verifier.

The pipeline mode is intentional: the published 0.1.0 CLI's `--recompute` needs
`attest.yaml`; a wrap-mode receipt cannot satisfy this verification path.

## Rotation and recovery

The private key is retained in the protected GitHub environment; GitHub does not
offer API retrieval of a stored secret. If it is lost or access is withdrawn,
create a new identity and update its public policy through a reviewed PR. Do not
silently replace the private key under an existing key identifier. Revoke a
compromised key with a recorded UTC revocation time, retain its public key and
history, and review which timestamped receipts remain acceptable. Never use
`--trust-receipt-timestamp` to bypass independent time evidence.

Key/TSA rotation requires updating the pinned policy and offline setup fixture,
repeating the negative verification checks, and updating the environment secret
before publishing. Keep previous public keys and issuer certificates so older
receipts can still be checked against their original trusted policy. No other
project's signing identity is changed by this setup.
