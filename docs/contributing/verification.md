# Verifying builds and releases

The published **0.2.0** distributions remain unchanged. Their original evidence is
listed in the [release notes](../releases/0.2.0.md). PyPI's Trusted Publishing
attestation identifies the publication; it is not a claim that the original build
had the additional controls described below.

## Evidence from subsequent CI builds

A successful protected `master` build produces:

- The tested wheel and sdist, plus `SHA256SUMS.json`.
- `ci-evidence.tar.gz`: exact source archive (including tests and workflows),
  `uv.lock`, project configuration, checksums, build environment details, runtime
  and validation CycloneDX SBOMs, JUnit results, branch coverage and mutation reports.
- `build-provenance.sigstore.json`: signed GitHub build provenance binding the
  two distributions and evidence archive to their source commit and CI run.
- `runtime-sbom.sigstore.json`: a signed statement binding the runtime SBOM to
  both distributions. SBOMs represent the **universal locked resolution**, including
  Python/platform alternatives; a user's installed dependency graph can differ.
- The separately audited dependency report from the successful Security run on
  the same commit.

Only an isolated signing job on a `master` push receives OIDC and attestation
permissions. It downloads the successful CI artifacts and does not execute
repository code. Pull requests do not receive signing permissions. The publish
workflow verifies provenance before forwarding the same distributions to PyPI.
After publication, it attaches the evidence files to the prepared GitHub release,
without overwriting existing assets. Actions retention is 90 days for these reports;
release attachments preserve the published evidence beyond that limit.

These controls apply to builds made **after** their introduction. They do not
retroactively establish build provenance for 0.2.0. A signed and RFC 3161 timestamped
**Attest receipt is not yet provided**. GitHub/Sigstore attestations must not be
presented as that additional receipt or as complete parity with continuum-attest.

## Check the identity as well as the hash

Download the distribution and evidence from the release you intend to verify.
Use its recorded commit as `EXPECTED_COMMIT`; do not use the current branch tip.
The identity is the CI workflow on this repository, on `refs/heads/master`:

```sh
gh attestation verify outerspace_apizr-VERSION-py3-none-any.whl \
  --bundle build-provenance.sigstore.json \
  --repo Alien6-Studio/outerspace-apizr \
  --signer-workflow Alien6-Studio/outerspace-apizr/.github/workflows/ci.yml \
  --source-digest EXPECTED_COMMIT --source-ref refs/heads/master
```

Repeat for the sdist and `ci-evidence.tar.gz`. The attestation verifies the subject
hash, signing identity and source revision. Compare the distribution hashes with
`SHA256SUMS.json` and the public PyPI metadata as a separate consistency check.
A self-computed hash alone does not establish the producer's identity.

Extract the verified source archive into a fresh directory to rerun its checks:

```sh
uv sync --locked --all-groups
uv run --locked pytest --cov --cov-report=term-missing
uv run --locked python scripts/security_mutations.py
uv run --locked --group security python scripts/audit_dependencies.py
uv run --locked --group docs mkdocs build --strict
```

Use the Python and uv versions recorded in `build-evidence.json`. The dedicated
OCI suite additionally needs the Linux Docker configuration and deliberately built
worker image in the archived CI workflow. OCI tests validate the same source
revision; their separately built image is not the published wheel's binary identity.
Do not count the repeated OCI samples as additional distinct test cases.

## Coverage and mutation controls

The 0.2.0 release measured global branch-aware coverage of 90.87%, 90.99%, 90.99%
and 90.65% on Python 3.11, 3.12, 3.13 and 3.14 respectively. The global floor is
now **90%**, in addition to the modern packages' individual 90% floors.
The legacy `src/apizr/modules/` aggregate measured 59.91%, 59.91%, 59.91% and
59.56%; its separate **59.5%** floor prevents modern coverage from hiding a legacy
regression. This is a regression floor, not a claim of sufficient legacy coverage.

The security mutation job first runs designated tests on unchanged code, then
removes one protection at a time in a disposable copy. Each mutant must fail its
designated assertion. Surviving mutants, skipped tests, collection errors, timeouts
and changed source anchors fail the gate. Its initial 17 mutations cover static
analysis, symlink confinement, artifact integrity, policy refusal and Docker
isolation/resource flags. This is a selected protection set, not exhaustive mutation
coverage or a substitute for the actual OCI boundary tests.

The eighteenth mutation disables local process-group termination while retaining
direct-worker termination. The ordinary-descendant test must detect the surviving
child's activity. Test cleanup runs only after the assertions and cannot make a
mutant pass.

## Observing local descendant termination

The local supervisor sends `SIGKILL` to the worker's process group and waits for
the direct worker. It cannot reap an orphaned grandchild. The descendant test
therefore observes disappearance or a zombie state within a two-second bound,
while requiring its heartbeat to remain unchanged. A persistent `D`, `R`, `S` or
`T` state, resumed activity, changed process group or failed observation fails the
test. Failure output preserves the timed state/group/parent observations and,
on Linux when available, pending-signal fields from `/proc`.

This replaces the single snapshot that once observed `D` in the Python 3.14 CI
run recorded in [#79](https://github.com/Alien6-Studio/outerspace-apizr/issues/79).
Linux documents `D` as an
[uninterruptible wait](https://docs.kernel.org/filesystems/proc.html); it is not
terminal evidence. The old run did not collect enough information to establish
why that state occurred. The bounded observation handles asynchronous scheduling
without accepting a stopped or blocked child as terminated. Separate tests reject
a real stopped child and simulated persistent nonterminal states. This changes
the verification procedure, not the runtime's termination behavior or its
[containment guarantees](../architecture/execution-policy-v1.md).
