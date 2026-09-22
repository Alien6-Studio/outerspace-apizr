# Changelog

## 0.3.0 — Unreleased

Repository release candidate: **0.3.0**. Latest published stable: **0.2.1**.

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
- Prepare final package metadata and release/migration notes without publication.

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
