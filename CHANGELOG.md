# Changelog

## 0.3.0 — Unreleased

- Begin development at `0.3.0.dev0`; the latest published stable release remains 0.2.1.
- Add Exposure Policy v1 and Exposure Plan v1 with explicit selection, digest-bound
  static evidence, fail-closed interface/execution checks and `apizr expose plan`.
- Add deterministic direct repository REST/MCP bundles from validated Exposure
  Plans, complete verified source packaging, qualified names and transactional
  `apizr expose build` output (#88). Existing Readiness eligibility remains
  unchanged.
- Add governed repository REST/MCP execution (#90): independently versioned
  multi-source plans and bridges, fresh local/OCI workers, per-call integrity
  validation, explicit repository worker image compatibility and shared Docker
  controls. Direct and single-source artifact bytes remain unchanged.

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
