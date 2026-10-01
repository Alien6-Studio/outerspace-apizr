# Homebrew build inputs

This prepares the supply chain for Lot 5. It does not deliver an Apizr Formula,
create a tap, or publish a package. All four packages remain `0.4.2rc1`.
Issue [#228](https://github.com/Alien6-Studio/outerspace-apizr/issues/228) remains
open until the actual Formula is implemented and qualified.

## Runtime provider

The proposed runtime uses Homebrew `python@3.14`, a system-site-packages virtual
environment and the official `pydantic` formula. The first qualification requires
Pydantic **2.13.5** and pydantic-core **2.46.5**. Import locations must resolve into
that formula's keg. The proof reproduces the dependency `.pth` written by
Homebrew's `virtualenv_create`, without modifying global Python files.

This is a different packaging contract from pip/uv: Homebrew owns Pydantic and
its runtime closure, and may update them. Future qualification must check
Apizr's public `pydantic>=2.12,<3` constraint and record exact tested versions.
There is no claim of permanent byte parity with `uv.lock`, and no artificial
versioned Pydantic formula. Python 3.14 is the Homebrew interpreter selection;
Apizr's supported Python range remains 3.11–3.14.

Official references: [Python formula guidance](https://docs.brew.sh/Language-Specific-Formulae),
[Pydantic formula](https://formulae.brew.sh/formula/pydantic), and
[Homebrew virtualenv API](https://docs.brew.sh/rubydoc/Language/Python/Virtualenv.html).

## Build-only inputs

`homebrew-build = ["hatchling==1.28.0"]` adds exactly two packages to the universal
lock: Hatchling 1.28.0 and trove-classifiers 2026.9.21.13. Existing packaging 26.3,
pathspec 1.1.1 and pluggy 1.6.0 complete the five-package closure. No existing
locked version changes. Python <3.11's conditional `tomli` dependency does not
apply to this repository's supported interpreters.

Hatchling 1.28.0 is the first stable minor after the declared 1.27 floor whose
reviewed metadata explicitly lists Python 3.14; 1.27.0 does not. This bounded
choice must pass the actual candidate build and current vulnerability audit.
The exact Hatchling source and wheel were reviewed, including its PEP 517 hooks,
dependency metadata and MIT notice. The exact trove-classifiers source and wheel
were reviewed as classifier data and a listing CLI under Apache-2.0. Its wheel
avoids executing its setuptools/calver source build. Preserve both complete
notices when redistributing build inputs. The dependency policy retains those
texts and binds the review to every newly locked artifact hash.

`policy/homebrew-build-inputs.json` separates the mutable Homebrew runtime
provider from checksummed build-only wheel identities. The generator traverses
the locked group, rejects ambiguous/conditional or non-universal artifacts, and
requires exact agreement with this reviewed policy. It checks downloaded hashes
and wheel metadata; no live-index version selection occurs.

```sh
uv run --locked python scripts/prepare_homebrew_build_inputs.py \
  --lock uv.lock --policy policy/homebrew-build-inputs.json \
  --output /tmp/apizr-homebrew-inputs
```

The new output contains `build-wheelhouse/` and deterministic `build-inputs.json`.
It is temporary build tooling, not content for Apizr archives, a Cellar runtime
prefix, or a plugin store. The dedicated `homebrew-build` audit has no advisory
exceptions. Release evidence includes its policy and dedicated SBOM, as well as
the complete validation SBOM.

## Offline architecture proof

The preserved entry candidate is `outerspace_apizr-0.4.2rc1.tar.gz`, SHA-256
`5b841b7f0e3d335330f6280b8409986036069371fe700282b18625940cf380b4`, from protected
commit `7af517627aa92009f8e0ece2d255e7e2fd98e529`. It is only the architecture
comparison. Final feature evidence must instead identify a coordinated candidate
produced once for the exact feature commit; macOS jobs consume the original
sdist bytes without rebuilding or recompressing it.

```sh
uv run --locked python scripts/homebrew_build_proof.py \
  --candidate /tmp/coordinated-candidate --source-sha EXACT_SOURCE_COMMIT \
  --inputs /tmp/apizr-homebrew-inputs --output /tmp/apizr-homebrew-proof
```

The proof keeps PEP 517 isolation enabled, sets `PIP_NO_INDEX=1`, uses only the
reviewed local `PIP_FIND_LINKS`, disables user pip configuration and starts with
an empty cache. macOS `sandbox-exec` denies network access for all descendants.
An audit observer records and refuses Python socket attempts, including in
pip's generated backend environments. Negative controls verify both layers;
the successful build must observe the requirements and wheel-building child
hooks with zero network attempts. A wrapper records actual dynamic PEP 517
requirements without changing them. Missing or unreviewed requirements fail;
there is no fallback to an index or disabled build isolation.

After wheel construction the temporary build environment is destroyed. A separate
fresh Homebrew-Python environment installs the wheel with `--no-deps` and checks
metadata, import provenance, runtime inventory, `apizr --version`, `apizr init`
and local `apizr doctor` with generated operator policy. Hatchling and
trove-classifiers must be absent. No Maturin, Flit, Hatch Fancy PyPI Readme, Rust
or Cargo closure belongs to this Apizr build toolchain; Homebrew remains
responsible for building its own Pydantic dependency.

The read-only **Homebrew build inputs** workflow runs on pull requests and manual
dispatch, with a narrowly scoped branch push trigger for qualification before
opening the preparation PR. The required build-input proof targets Apple Silicon
on `macos-26`. Intel provisioning is not a required PR job. Linux Homebrew runtime
and Formula installation are not qualified by this proof. No final Formula or
public tap should be inferred from a successful build-input receipt.

## Homebrew distribution qualification boundary

Apizr 0.4.2 Homebrew qualification targets current Homebrew Tier-1 macOS,
which in the October 2026 support window is Apple Silicon. The intended host
must meet Homebrew's complete Tier-1 requirements, including supported macOS,
physical Apple hardware, a compatible prefix and official dependency bottles.
Homebrew Python 3.14 and Pydantic satisfying `>=2.12,<3` are required; the exact
versions and import provenance used in each proof remain recorded.

Intel macOS is Homebrew Tier 3 and **not qualified** by Apizr's Homebrew
distribution. It is documented and non-blocking for this preparation. Linux
Homebrew runtime is also **not qualified in 0.4.2**. This narrower distribution
boundary does not change Apizr's Python 3.11–3.14 compatibility declaration.

`policy/homebrew-qualification.json` is a separate, strictly validated
`apizr.homebrew-qualification/v1` contract. Unknown, duplicate, missing or
contradictory classifications are rejected. The build-input policy, lock,
wheel identities and historical manifest remain byte-for-byte unchanged;
the manifest SHA-256 remains
`c981a11d84ec319cd10d156b18b31e073ca480e1f2b62f3880c4a17cac0f5405`.
The boundary validator binds its deterministic receipt to that manifest, and
release evidence archives both policies.

GitHub's [hosted macOS runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
are virtual machines. `macos-26` supplies an ARM64 CI proof for the intended
target; it is **not itself certified as a Homebrew Tier-1 host**. A separate
physical Apple Silicon Mac proof is required before this preparation PR opens.
Its host receipt records only a physical-host classification, architecture,
macOS and provider versions, relative import locations and qualification results.
Hardware probes are reduced to a classification; device identifiers and private
paths are not retained. It consumes the same candidate bytes and reviewed
wheelhouse as CI, and applies the unchanged offline build and runtime acceptance
criteria.

The upstream audit on 2026-10-01 used Homebrew's
[Support Tiers revision 5cec100](https://github.com/Homebrew/brew/blob/5cec10029857fd8082da6b11bac5878419f4772a/docs/Support-Tiers.md)
(commit dated 2026-09-23; document review date 2026-09-21). It lists
“Intel x86_64 systems running macOS” under Tier 3, without full CI coverage or
regular bottle production. Apple Silicon macOS 15, 26 and 27 are in its current
Tier-1 OS window, subject to all configuration requirements.

The official
[Pydantic formula revision 433eb8a](https://github.com/Homebrew/homebrew-core/blob/433eb8a8d09d686819326f5f03f9ed98eaf18287/Formula/p/pydantic.rb)
provides Pydantic 2.13.5 bottles for Apple Silicon macOS and Linux, but none for
Intel macOS. The formula source SHA-256 from the official API is
`78b3164fbc745cfceb19330c2140b80243709c27b063a383d5cfbc6d7ad60097`.
These are dated upstream observations, not immutable future provider guarantees.

### Preserved Intel evidence

The [first Intel job](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36893243632/job/110473963051)
correctly refused the runner's stale Pydantic 2.13.4. After refreshing Homebrew,
the [updated provisioning job](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36894062277/job/110476711279)
entered the native dependency bootstrap for OpenSSL, Python, LLVM, Rust and
Pydantic. It reached the unchanged 45-minute job limit during LLVM compilation,
before Pydantic 2.13.5 became available to the runtime-provider preflight.
The equivalent final-head Intel attempt was then canceled; its records remain
in [run 36897250817](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36897250817)
and issue #228.

This is an **UPSTREAM PLATFORM QUALIFICATION LIMITATION**. It did not reach
Apizr's isolated PEP 517 build and is not evidence of a build-closure failure
or success on Intel. No retry-until-green, relaxed provider version,
`continue-on-error`, or extended bootstrap timeout is used.
Intel qualification can be revisited if Homebrew restores a usable supported
provider path or Apizr intentionally adopts a separately maintained Intel
strategy; neither is part of the 0.4.2 commitment.

### Preserved Apple Silicon evidence

The [Apple Silicon job](https://github.com/Alien6-Studio/outerspace-apizr/actions/runs/36897250817/job/110487561371)
passed at `78a3d87de13bb5767584cd90c4f125c1d85ab2cb` with Homebrew 7.0.7,
Python 3.14.8, Pydantic 2.13.5 and pydantic-core 2.46.5. Its original candidate
sdist SHA-256 is
`a707f8fbd486106c48550fd82f666f6d8bf28b20c65c30f24d2a3fb22e5abb01`;
the resulting wheel SHA-256 is
`8528c0f4e50cff41238b74da6c709c0f217e06cf35bef9ba707fee9d470be9ab`.
The isolated build observed no dynamic requirements or network attempts;
the separate runtime passed version, init and doctor after build-environment
destruction. These historical bytes and receipts remain unchanged. The boundary
correction must receive a new exact-head proof through the normal workflow.

### Physical Apple Silicon proof

`policy/homebrew-physical-qualification.json` retains the sanitized physical
proof for the original candidate above. It passed on macOS 27.0.1 with Homebrew
7.0.7, Python 3.14.8, Pydantic 2.13.5 and pydantic-core 2.46.5. The current patch,
physical Apple Silicon host, internal storage, default prefix and official
provider bottles satisfy the audited Homebrew Tier-1 host requirements.

The isolated build produced the identical wheel SHA-256 recorded above, with
no dynamic requirements and zero observed network attempts. Both network-refusal
controls passed. After the build environment was destroyed, the fresh runtime
installed only Apizr with `--no-deps`, imported Pydantic from the Homebrew keg,
contained no Hatchling or trove-classifiers, and passed version, init and doctor.

This receipt qualifies exact candidate bytes, not an arbitrary later commit.
After committing this boundary correction, the new coordinated candidate's core
sdist hash must equal the physically tested hash. If it differs, repeat the
physical proof on the new bytes before opening the preparation PR. Hosted CI
also qualifies the exact new head independently. Neither receipt qualifies a
production Formula.
