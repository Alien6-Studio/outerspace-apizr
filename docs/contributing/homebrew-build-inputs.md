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
opening the preparation PR. It targets macOS arm64 and maintained
`macos-26-intel`; actual results, including infrastructure limitations, belong
in the qualification receipt. Linux Homebrew and Formula installation are not
qualified by this proof. No final Formula or public tap should be inferred from
a successful build-input receipt.
