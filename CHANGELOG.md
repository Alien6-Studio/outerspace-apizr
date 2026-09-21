# Changelog

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
