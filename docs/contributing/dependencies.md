# Dependency maintenance policy

Changes to dependencies are reviewed through the protected pull-request process,
including Dependabot updates. An available update is not an instruction to merge
it. Keep runtime dependency changes separate from release and documentation work.

## Sources and integrity

All third-party locked packages must resolve from `https://pypi.org/simple`.
Distribution URLs must use HTTPS on `files.pythonhosted.org`, with SHA-256 hashes
recorded in `uv.lock`. The only local editable package is Apizr itself at `.`.
Git dependencies, arbitrary indexes, direct URLs and additional local packages are
rejected by `scripts/check_dependency_sources.py` in the required dependency job.
A source exception requires an explicit policy change in a reviewed PR; there is
no automatic fallback index.

Export and audit the complete universal lock, including Python/platform variants,
for runtime, development, documentation and security tooling. Findings and report
collection failures block. Do not silently add ignored advisories. Preserve the
reports and review the runtime and validation SBOMs when a graph changes.

## Licenses and package selection

Before adding or changing a dependency, review its license and required notices
at the **selected version**, its source, maintenance status, purpose and transitive
cost. Record that review in the dependency PR. Preserve license/attribution files
required for redistribution. Reject dependencies with no identified license or
terms incompatible with the intended GPL-3.0-or-later distribution until a
maintainer has resolved the issue and recorded the decision. Do not treat package
metadata or an SBOM entry as a legal compatibility determination.

License review is currently a **maintainer review requirement**, not an automated
SPDX allowlist equivalent to Attest's `cargo-deny` configuration. There is not yet
a reviewed per-package license inventory or named-package denylist. This remains
a gap in complete policy parity; the source and vulnerability checks above are
automated and blocking.
