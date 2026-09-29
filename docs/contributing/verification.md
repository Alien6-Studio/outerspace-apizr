# Verifying builds and releases

The published **0.2.0** distributions remain unchanged. Their original evidence is
listed in the [release notes](../releases/0.2.0.md). PyPI's Trusted Publishing
attestation identifies the publication; it is not a claim that the original build
had the additional controls described below.

## Evidence from subsequent CI builds

A successful baseline `master` build, or a protected `release/0.4.1` push
with the governance workflow, produces:

- For coordinated candidates: four tested wheels and four sdists, plus
  `SHA256SUMS.json` and the commit-bound candidate inventory. Earlier releases
  contain the core wheel/sdist pair only.
- `ci-evidence.tar.gz`: exact source archive (including tests and workflows),
  `uv.lock`, project configuration, checksums, build environment details, runtime
  and validation CycloneDX SBOMs, JUnit results, branch coverage and mutation reports.
- `build-provenance.sigstore.json`: signed GitHub build provenance binding the
  distributions and evidence archive to their source commit and CI run.
- `runtime-sbom.sigstore.json`: a signed statement binding the runtime SBOM to
  core wheel and sdist. Plugin dependency identities are recorded separately in
  target-specific wheelhouses, requirements and catalog inventories. SBOMs represent the **universal locked resolution**, including
  Python/platform alternatives; a user's installed dependency graph can differ.
- The separately audited dependency report from the successful Security run on
  the same commit.

Only an isolated signing job on a `master` push or an explicitly protected
`release/0.4.1` push receives OIDC and attestation permissions. The release-line
protection is a [pending maintainer action](release-branches.md#required-maintainer-action);
unprotected release pushes cannot sign. It downloads the successful CI artifacts and does not execute
repository code. Pull requests do not receive signing permissions. The publish
workflow verifies provenance before forwarding the same distributions to PyPI.
After publication, it attaches the evidence files to the prepared GitHub release,
without overwriting existing assets. Actions retention is 90 days for these reports;
release attachments preserve the published evidence beyond that limit.

These controls apply to builds made **after** their introduction. They do not
retroactively establish build provenance for 0.2.0. **The published 0.2.1 release
includes a signed and RFC 3161 timestamped Attest delivery receipt**, independently
verified offline against the repository trust store. Its exact source, CI run,
hashes and publication checks are in the [0.2.1 release record](../releases/0.2.1.md).
See the [managed identity and receipt verification](attest.md) for the five
required checks. GitHub/Sigstore attestations are separate build evidence;
the delivery receipt does not claim that Attest supervised the earlier build.

## Check the identity as well as the hash

Download the distribution and evidence from the release you intend to verify.
Use its recorded commit as `EXPECTED_COMMIT`; do not use the current branch tip.
The identity is the CI workflow on this repository. Historical releases through
0.4.0rc1 use `refs/heads/master`; 0.4.1 candidates/final require exactly
`refs/heads/release/0.4.1`. Set `EXPECTED_SOURCE_REF` to the recorded approved
identity, never to an arbitrary branch supplied by an artifact:

```sh
gh attestation verify outerspace_apizr-VERSION-py3-none-any.whl \
  --bundle build-provenance.sigstore.json \
  --repo Alien6-Studio/outerspace-apizr \
  --signer-workflow Alien6-Studio/outerspace-apizr/.github/workflows/ci.yml \
  --source-digest EXPECTED_COMMIT --source-ref "$EXPECTED_SOURCE_REF"
```

Repeat for every distribution in that release and `ci-evidence.tar.gz`. The attestation verifies the subject
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
worker image in the archived CI workflow. Coordinated qualification builds this
image from the retained core wheel and records its role, wheel hash and image/config
digest in `validation-oci`. That digest identifies a disposable worker image, not
a published registry manifest or a generated user service.
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

## Git interruption regression

The Git runner records the default main-thread SIGINT request and raises
`KeyboardInterrupt` only at its own checkpoints, after subprocess construction
has transferred ownership and outside Python's internal waitpid lock. The handler
stays active through cleanup, then the caller's handler is restored. Custom
handlers and worker-thread calls retain their existing behavior. Cleanup still
uses the same two-second deadline; unconfirmed cleanup remains a failure.

`tests/git_source/test_sigint.py` injects a real SIGINT during subprocess
construction, while the waitpid lock is acquired, and during final cleanup. It
checks child reaping, closed streams, an unlocked wait lock, handler restoration
and reuse. The construction and wait-lock cases fail against the earlier runner.
The existing fixed 25 Git/worker repetitions remain unchanged and retain every
outcome, including failures; no retry-to-green or deadline increase is used.
