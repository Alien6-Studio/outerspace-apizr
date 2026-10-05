# Verifying builds and releases

This section is for contributors and operators who need to inspect release
provenance or prepare a verified offline installation. For everyday use, start
with [Install Apizr](../getting-started/install.md).

## Prepare a verified installation workspace

These commands download the published 0.4.4 packages and a complete dependency
export. They do not build or publish anything. Use this workspace for the
[offline installation and plugin profiles](../getting-started/install.md#choose-a-plugin-profile).

You need Python, tar and GitHub CLI (`gh`). Choose your interpreter and export
from [Supported targets](../getting-started/install.md#supported-targets).
Managed plugin installation also needs **uv 0.12.0** on `PATH`; check `uv --version`
before continuing. The commands retain the original archive bytes and compare
both hashes and provenance before using the dependency export.

This selection uses Linux x86-64 / Python 3.11. The published inventory supplies
the exact patch-level export and source commit. Keep all files from the same release:

```sh
export APIZR_VERSION=0.4.4
export RELEASE_TAG=v0.4.4
export PYTHON=python3.11
export TARGET_PATTERN="apizr-${APIZR_VERSION}-linux-x86_64-cpython-3.11.*.tar.gz"
mkdir -p release/assets release/candidate/dist release/target-download
export EXPECTED_COMMIT=$(gh api "repos/Alien6-Studio/outerspace-apizr/commits/$RELEASE_TAG" --jq .sha)
gh release download "$RELEASE_TAG" --repo Alien6-Studio/outerspace-apizr --dir release/assets \
  --pattern candidate.json --pattern release-assets.json --pattern SHA256SUMS \
  --pattern 'outerspace_apizr*' --pattern "$TARGET_PATTERN" \
  --pattern ci-evidence.tar.gz --pattern build-provenance.sigstore.json
gh attestation verify release/assets/ci-evidence.tar.gz \
  --bundle release/assets/build-provenance.sigstore.json \
  --repo Alien6-Studio/outerspace-apizr \
  --signer-workflow Alien6-Studio/outerspace-apizr/.github/workflows/ci.yml \
  --source-digest "$EXPECTED_COMMIT" --source-ref refs/heads/master
```

Bind the selected export and candidate inventory to the attested CI evidence,
then verify the eight package hashes and the downloaded checksum entries. Local
copies below preserve the exact bytes and provide the layout used by the offline
commands; they do not reconstruct any package:

```sh
"$PYTHON" - <<'PYTHON'
import fnmatch
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
assets = Path("release/assets")
candidate = Path("release/candidate")
inventory = json.loads((assets / "release-assets.json").read_text())
assert inventory["version"] == os.environ["APIZR_VERSION"]
assert inventory["commit"] == os.environ["EXPECTED_COMMIT"]
assert inventory["source_ref"] == "refs/heads/master"
checksums = dict(line.split("  ", 1)[::-1] for line in (assets / "SHA256SUMS").read_text().splitlines())
for path in assets.iterdir():
    if path.name != "SHA256SUMS":
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == checksums[path.name]
exports = [item for item in inventory["artifacts"] if fnmatch.fnmatch(item["file"], os.environ["TARGET_PATTERN"])]
assert len(exports) == 1, "Select exactly one qualified target export"
export = exports[0]
assert export["evidence_member"].startswith("coordinated/release-target-")
assert export["evidence_member"].endswith("/target-export.tar.gz")
with tarfile.open(assets / "ci-evidence.tar.gz") as evidence:
    def approved(member, path):
        source = evidence.extractfile("./" + member)
        assert source is not None
        with path.open("rb") as local:
            assert hashlib.file_digest(local, "sha256").hexdigest() == hashlib.file_digest(source, "sha256").hexdigest()
    approved("coordinated/release-candidate/candidate.json", assets / "candidate.json")
    approved(export["evidence_member"], assets / export["file"])
manifest = json.loads((assets / "candidate.json").read_text())
assert manifest["commit"] == os.environ["EXPECTED_COMMIT"]
assert manifest["version"] == os.environ["APIZR_VERSION"]
assert len(manifest["artifacts"]) == 8
for item in manifest["artifacts"]:
    name = Path(item["file"]).name
    path = assets / name
    assert path.stat().st_size == item["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    shutil.copyfile(path, candidate / "dist" / name)
shutil.copyfile(assets / "candidate.json", candidate / "candidate.json")
shutil.copyfile(assets / export["file"], "release/target-download/target-export.tar.gz")
print("Verified release candidate and complete target export")
PYTHON
mkdir release/target
tar -xzf release/target-download/target-export.tar.gz -C release/target
export CANDIDATE="$PWD/release/candidate"
export TARGET="$PWD/release/target"
export CORE_DIR="$PWD/core"
```

Inspect the qualification report and `target.json` before installation: your
interpreter must match the recorded target. Release engineers can still use
[Actions artifacts for exact qualification](releases.md); PR
previews cannot substitute for the final release's attested resources.

`target.json` records the actual Python patch version, system and architecture.
Its file inventory covers catalogs, locks, notices inside wheels and dependency
bytes. Do not substitute other wheels after verification.

Continue in this same directory and terminal with
[plugin profile installation](../getting-started/install.md#choose-a-plugin-profile)
or the [offline core alternatives](../getting-started/install.md#install-the-core-offline).
If the core is already installed elsewhere, set `CORE_DIR` to that environment's
absolute path before following the plugin commands.

## Historical release evidence

The published **0.2.0** distributions remain unchanged. Their original evidence is
listed in the [release notes](../releases/0.2.0.md). PyPI's Trusted Publishing
attestation identifies the publication; it is not a claim that the original build
had the additional controls described below.

## Evidence from subsequent CI builds

A successful protected `master` push with the governance workflow produces:

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

Only an isolated signing job on a protected `master` push receives OIDC and
attestation permissions. The completed release branches are retired; their
original signed evidence retains its recorded source refs. See the
[active branch policy](release-branches.md). Development build provenance does not
authorize candidate qualification or publication. It downloads the successful CI artifacts and does not execute
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
identity, never to an arbitrary branch supplied by an artifact. Retiring the old
branch does not change the source ref recorded in its signed evidence; do not
substitute `release/0.4.2` when verifying published 0.4.1 archives:


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

## 0.4.4 publication record

**0.4.4 is published and verified.** Core, OCI, MCP and Attest are coordinated at
0.4.4. PyPI publication completed on 4 October 2026; the complete immutable
GitHub release was published on 5 October after independent public-installation
checks. The official MCP Registry descriptor is published too.
Published 0.4.3 and its original archives, tags and provenance remain unchanged.
Tracking: [#246](https://github.com/Alien6-Studio/outerspace-apizr/issues/246) and
[PR #247](https://github.com/Alien6-Studio/outerspace-apizr/pull/247).

The immutable source is **`46c573d7f808f8d491cde1062d474b145288697f`**, the signed
protected-master squash merge of PR #247. The [public release](https://github.com/Alien6-Studio/outerspace-apizr/releases/tag/v0.4.4)
retains the original final CI archives, six complete target exports, signed
provenance, timestamped delivery receipt and independent verification records.
The source tag and those bytes remain unchanged by this documentation update.

| Verification | Retained result |
| --- | --- |
| Final qualification | [CI 37222486067](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/37222486067): all 25 jobs passed on the exact source, including six Linux/macOS targets, registry delivery, provenance and attachment verification |
| Security | [37222486038](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/37222486038): passed; the first dependency audit hit a PyPI TLS timeout and produced no report; only that failed job was rerun, with unchanged source and requirements |
| Documentation | [37222486108](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/37222486108): passed on the release source |
| Protected publication | [37223902790](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/37223902790): verification, separately approved receipt and upload, public comparison and durable evidence archival passed |
| Public installations | Fresh pip, uv tool and pipx installs outside checkout passed; all three managed plugins installed/activated separately with an unchanged minimal core; REST/MCP and A/B examples passed |
| Independent receipt | Offline expected-identity, signature, timestamp, schema, consistency and recomputation checks passed, with no warnings |
| Official MCP Registry | [37268211755](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/37268211755): exact 0.4.4 descriptor published and independently read back |
| Homebrew tap | [Tap PR #2](https://github.com/Alien6-Studio/homebrew-tap/pull/2) merged as `dcecefbe64ea9ac16bcee7ca480ed0c582a57ace`; [public-source qualification 37268409503](https://github.com/Alien6-Studio/homebrew-tap/actions/runs/37268409503) passed style, readall, strict online audit, actual Formula install/test, CLI and runtime-provider isolation on a hosted Apple Silicon VM |

All eight unauthenticated GitHub downloads and all eight PyPI downloads match the
selected CI bytes. The [archive inventory](https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.4/candidate.json),
[checksums](https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.4/SHA256SUMS),
[public-installation report](https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.4/public-installations.json)
and [release verification](https://github.com/Alien6-Studio/outerspace-apizr/releases/download/v0.4.4/release-verification.json)
retain the exact identities and outcomes. The operator preflight refused a
different local uv version before installation; isolated, verified uv 0.12.0
was then used, without changing Homebrew or injecting tooling into the core.

The generated Homebrew Formula SHA-256 is
`e4106549787eca2f70c6be5523a6984a931f9baea6ce69cd797cd4e88adc2b30`;
its original core sdist is
`b536b1ddebae627315721f92645b48b59c6fa4e217ac76931cc41d412caed046`.
The final sdist also passed an isolated offline build and separate Homebrew
runtime proof on a physical Apple Silicon Mac. That architecture proof is not
physical Formula installation qualification. Hosted and physical evidence are
not relabeled, and the operator's existing Homebrew installation was preserved.

### Exact-source publication policy

Only **0.4.4 from protected `refs/heads/master`** is admitted by the new policy.
The selected source is the final signed squash-merge commit of PR #247, not its
PR test merge or the earlier candidate head. Record its full SHA, the exact
successful push CI run and all eight original archive hashes before tagging.
CI, Security and Documentation must pass on that same source and repository;
PR/manual runs, another ref, an unprotected branch, incomplete qualification and
later failed Security/Documentation runs cannot authorize publication.

The final CI builds a separate set of four wheels and four sdists once. All six
Linux/macOS target installations, disposable registry delivery, product checks,
signed provenance and verified release assets must pass. A protected master
push may stage provenance-verified 0.4.4 assets; PRs and other versions remain
previews. Staging never uploads packages or creates a release.

After those checks, `v0.4.4` must resolve to the exact selected source. The manual
PyPI workflow verifies that tag, source, CI run, original bytes and provenance,
then requires the existing separate protected receipt and publication approvals.
It publishes core → OCI → MCP → Attest using Trusted Publishing, compares all
public hashes and archives the signed timestamped receipt. Public installations
outside the checkout are verified before declaring delivery complete. The MCP
Registry descriptor selects 0.4.4, but its separate OIDC publication waits for the
matching public packages and verified GitHub release assets. It requires explicit
tag and full source SHA inputs; no previous release is selected by default.

The official Homebrew tap update is also bound to the final core sdist and
protected master provenance. Publication-mode rendering requires the public
immutable release asset to match the signed source; the generated Formula must
pass the tap review, audit and real Apple Silicon installation checks before its
update. Existing physical/hosted candidate evidence is not relabeled as final
public installation evidence. No Linux or Intel Homebrew runtime qualification
is claimed.

The frozen candidate source `3ddd068e64dd2f5a8148d77a0f4e7a2e2eeb5d46`, its
original four wheels/four sdists, hashes and qualification evidence remain
unchanged in `release-evidence/0.4.4-candidate/`. Final source qualification and
publication records are retained separately in `release-evidence/0.4.4-final/`.
Independent sdist rebuilds are tests and never replace selected upload bytes.

### Trunx integration qualification

On 5 October 2026, the Trunx operator confirmed qualification of the published
Apizr 0.4.4 integration: REST/MCP publication, signed proofs, ingestion,
consumption by immutable references and approval governance. A/B results conform
and the delivery CI job succeeds with native Docker, without a Trunx adapter.
No additional blocking Apizr correction was requested. This status is the
operator's report; Apizr's disposable registry tests remain separate evidence.

<details markdown="1">
<summary>Earlier staging observations</summary>

Human approvals for MCP A/B were previously verified in Trunx beta on
`attest-e2e` / `qualification-044`. Two immediate REST B rechecks failed with
`admission_failed` then `remote_state_unconfirmed`; later explicit resumes
reportedly completed against the same image/proof without a new build/signature.
Their cause was not isolated. These historical failures and recovery remain
retained separately and were not established as a generic Apizr defect.

</details>
