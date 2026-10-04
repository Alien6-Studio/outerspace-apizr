# Changelog

## 0.4.4 — Unreleased candidate

- Export and verify existing capability/bundle JSON evidence without importing
  business code, optionally checking its exact existing OCI build lineage.
- Confirm ambiguous Docker manifest-absence diagnostics through bounded,
  authenticated HTTPS before first publication; reject uncertain responses.
- Publish structural schemas for existing delivery results and document the
  external governance handoff, technical admission boundary and A/B example.
- Coordinate the four candidate packages at 0.4.4; no public release is claimed.

## 0.4.3 — 2026-10-02

- Declare the OuterSpace Apizr maintainer for Glama and add the Official MCP
  Registry identity and PyPI ownership metadata for 0.4.3.
- Add an MCP package console launcher that preserves explicit plugin activation,
  operator policy checks and the existing isolated stdio process.

## 0.4.2 — 2026-10-02

- Close both worker pipes even when process-group termination or another pipe
  closure fails, preserving failure reporting and preventing leaked descriptors.

- Initialize safe project configuration with explicit local analysis authority,
  diagnose local preparation read-only, and complete modern CLI commands in bash,
  zsh and fish.
- Generate deterministic current-native Postman, Bruno and Insomnia collections
  from verified REST bundles, with safe local regeneration of owned trees.
- Add opt-in MCP status/run/resume over an operator-selected existing delivery
  request, using the existing coordinator, captured policy and plugin store.
- Preserve the three default read-only tools and isolate per-operation authority.
- Advertise the installed MCP package version; coordinate all four packages and
  exact internal pins at 0.4.2.

- Validate local repositories and generate REST/MCP bundles through forge-neutral
  `apizr ci`, with explicit analysis authority and portable retained evidence.
- Add a real GitHub composite Action and structurally validated, self-contained
  GitLab CI/CD Component source. GitLab hosted runtime and catalog publication
  have not been performed.

- Add the core-only Apizr Homebrew Formula, a deterministic local/public source
  renderer, and real Apple Silicon installation and plugin-isolation qualification.
  Post-release integration publishes the official Alien6 tap after a real public
  Apple Silicon install/test and isolated-plugin proof. Intel macOS (Tier 3) and
  Linux Homebrew runtime remain unqualified.

Source-to-build MCP orchestration remains future work.

## 0.4.1 — 2026-09-29

Published and verified as `v0.4.1`, source
`d08b37d126957593a82784ef3ad096e3f8b4929d`. Qualification #203 and publication #204
record the eight original archives and their public-byte verification. See the
[release record](https://apizr.outerspace.sh/releases/0.4.1/#publication-status).

- Apply optional or required proof per delivery plan; required image transfer
  withholds the destination tag until independent proof verification and admission.
- Deliver one immutable build to up to eight explicit OCI destinations, preserving
  independent results, partial failure and evidence-based resume without rebuilding.
- Define release scope by generic OCI capabilities. Live-provider qualification
  is optional interoperability validation, not a remaining functional requirement.

- Bind durable source provenance, existing analysis/bundle identities and exact
  wheel closure into an immutable delivery plan consumed by OCI builds.
- Link the observed image to a separate delivery manifest, push and signed
  Attest proof while preserving historical v1 proof verification.

- Add optional explicit application dependency pins and resource files to project
  configuration and generated direct REST/MCP bundles.
- Reuse the OCI builder with the verified server/application closure and resource
  identities; qualify calls after removing the original source repository.
- Keep core and plugin environments isolated.

## 0.4.0rc1 — 2026-09-28 (release candidate)

- Publish official plugins as `outerspace-apizr-oci`, `outerspace-apizr-mcp` and
  `outerspace-apizr-attest`, with matching core and internal package requirements.
- Recognize the prefixed MCP and operator identities while preserving existing
  installations and exact-identity operator grants.
- Qualify and publish the coordinated replacement without reusing PyPI files.
  The functional 0.4.1 release remains separate; documentation stays in 0.4.

### Superseded core-only 0.4.0 upload — 2026-09-28

The core-only PyPI upload was removed after coordinated plugin publication did
not complete. It was not a coordinated final release. The functionality below
was delivered in **0.4.0rc1**, with the corrected package identities. See the
[0.4.0rc1 notes](https://apizr.outerspace.sh/releases/0.4.0/).


### Added

- Shared Python compiler operations and explicit `apizr.toml` configuration.
- HTTPS and SSH Git snapshots with explicit revisions, trust and bounded static
  source export; Git remains part of the minimal core.
- Isolated extension invocation, local/HTTPS installation with hashes, locked
  local dependencies, activation, invocation, removal and controlled updates.
- Project plugin declarations/locks, additive synchronization and catalog profiles.
- Optional local MCP analysis/planning, OCI service image build/push and Attest
  delivery signing, verification and OCI-linked proof transport.
- Independent operator grants for Git acquisition, source analysis, image
  construction, delivery signing and publication across managed entry points.

### Changed

- Repository filesystem analysis now requires an explicit `source.analyze` grant
  in CLI/Python and MCP. Fetching a Git snapshot does not grant analysis access.
- MCP analysis sessions retain captured scope and authority; policy changes need
  a restart. Project declarations and plugin activation grant no permissions.

### Fixed

- Generated MCP servers return object-valued `structuredContent` for every result
  shape, including scalars, arrays and null. Regenerate existing bundles to apply
  the fix; REST and Python result values remain unchanged.
- Process-group cleanup and explicitly synchronized descendant tests cover
  macOS extension/Git refusals and worker recovery without weakening cleanup errors.

### Compatibility and scope

- Keep Python 3.11–3.14, minimal Pydantic-only core, explicit exposure selection,
  single-source commands, historical YAML pipeline and direct/local/OCI boundaries.
- Defer application dependencies/resources, shared manifest, multiple destinations,
  mandatory proof to 0.4.1. MCP delivery,
  Postman, forge integrations, onboarding tools and the Homebrew tap belong to 0.4.2.

## 0.3.0 — 2026-09-22

Published from `43f5626fe9e26b018aa323abd83b9611f7b2aba9`, using the exact artifacts
from master CI run `35735875051`. See the [verified delivery](https://apizr.outerspace.sh/releases/0.3.0/#verified-delivery).

### Added

- Explicit Exposure Policy/Plan v1 over digest-bound repository evidence.
- Multi-module repository REST/MCP bundles with qualified public names, verified
  source imports, private helpers and atomic generation.
- Governed repository local/OCI execution with independent runtime/bridge v1/v2
  contracts, fresh workers per invocation and per-call artifact verification.
- Optional notebook/HTTP/MCP/legacy dependency extras with an isolated minimal compiler install (#63).
- Declarative notebook cell tags, requirements and data files, with a complete conversion example (#16).
- Explicit legacy Docker builds/resource packaging and installed pipeline plugins (#1, #15).
- Separate lexical class/method inventory; no change to top-level capability exposure (#5).
- Opt-in Linux OCI subprocess-deny worker profile, including thread prohibition (#49).

### Changed

- Make discovery → readiness → explicit selection → exposure → execution the main
  README, Start Here, homepage and CLI journey; add small policy examples.
- Publish reviewed package metadata and release/migration notes.

### Security / execution boundaries

- Reuse reviewed process cleanup and Docker controls; require the repository worker
  image protocol and immutable identity. OOM classification requires provider evidence.
- Preserve trusted-code boundaries: local processes do not isolate filesystem/network;
  OCI is not a VM. Its strict opt-in worker profile prohibits process/thread creation
  before project imports; default allow mode and local mode retain their behavior.
- Preserve the 18 security mutants and add two targeted strict-profile mutations.

### Compatibility

- Preserve direct repository artifacts, all single-source contracts/goldens, existing
  Readiness eligibility and default notebook conversion.
- Default installation is now minimal: select `[legacy]` to keep the full 0.2.1
  dependency stack. Existing dependency versions and archive hashes stay frozen.
- Selected ambiguous legacy definitions/overloads and duplicate routes now fail
  before generation; select a single wrapper or exclude ambiguity (#28).

## 0.2.1 — 2026-09-21

### Verification and release evidence

- Require bounded terminal evidence and no surviving activity for ordinary worker
  descendants; retain process-state diagnostics when verification fails (#79).
- Enforce 18 security mutation checks, a 90% global branch-coverage floor, a
  separate measured legacy floor, and macOS validation.
- Archive exact source/lock, runtime and validation SBOMs, tests, coverage and
  dependency reports with verified CI provenance.
- Sign and RFC 3161 timestamp release-delivery receipts using the managed Apizr
  identity; verify receipt identity, timestamp and artifact hashes before upload.
- Enforce reviewed license expressions, archive fingerprints, scoped exceptions
  and denied-package policy for every version in the universal dependency lock.

### Documentation and maintenance

- Remove Google Analytics from documentation; optional GitHub statistics remain
  off by default. Adopt DCO 1.1 for new contributions and document best-effort
  maintenance/disclosure without guaranteed response deadlines.
- Clarify immutable published files versus later verification builds, restore
  the repository release display, credit third-party assets and remove the
  obsolete Product Hunt promotion.
- Update pinned GitHub Actions dependencies.

The Python 3.11–3.14 and application contracts are unchanged. The descendant
change strengthens verification; it does not establish the cause of the older
failure or change the process runtime. See the [maintenance notes](https://apizr.outerspace.sh/releases/0.2.1/).

## 0.2.0 — 2026-09-21

### Added

- Static Capability IR and readiness for typed top-level Python functions and notebooks.
- Deterministic repository Scanner/Catalog, Capability Graph and Repository Readiness.
- REST and MCP generation from shared interface contracts.
- Experimental governed local execution, OCI execution and governed REST/MCP.

### Changed

- Apizr is presented as a capability compiler; discovery and contracts precede transports.
- Python 3.11–3.14, standard package metadata and installed-wheel operation.
- Current documentation, migration guidance and deliberate artifact-based publication.

### Security

- Dependency security floors, locked audits, CodeQL and required CI/container/OCI checks.
- Explicit trust boundaries: static analysis does not execute source; direct servers do.
  Local processes do not isolate host filesystem/network access; OCI is not a VM.

### Compatibility

- The notebook/script → FastAPI/container pipeline remains supported.
- Python 3.8–3.10 are no longer supported. Non-empty output directories are refused.
- Class/method capabilities and absolute subprocess prohibition remain unsupported.
- Legacy duplicate definitions/overloads remain a known limitation (#28).

See the [release notes](https://apizr.outerspace.sh/releases/0.2.0/) and
[compatibility guide](https://apizr.outerspace.sh/getting-started/developer-guide/releases/).
