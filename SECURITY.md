# Security policy

## Supported versions

Security fixes target the maintained 0.4.x line. Apizr 0.4.6 and generated targets
support **Python 3.11–3.15**. Use a supported interpreter and keep dependencies updated.
See the [compatibility notes](docs/getting-started/developer-guide/releases.md).

The current resolved runtime and tooling graphs pass the vulnerability audit.
This is a dated database result, not a guarantee of vulnerability-free software;
rerun the audit regularly and after dependency changes.

## Report a vulnerability privately

Use GitHub's [Report a vulnerability](https://github.com/Alien6-Studio/outerspace-apizr/security/advisories/new)
form. Private vulnerability reporting is enabled for this repository (verified
2026-09-20). Include affected versions, reproduction steps, impact and a minimal
proof of concept. Do not publish exploit details, credentials or personal data
in a public issue. There is no promised response SLA or paid security service.
If the form is unavailable, use the public issue tracker only to request that
a private reporting channel be restored, without disclosing vulnerability details.

Maintenance is provided on a best-effort basis by the current maintainer. There
is no guaranteed acknowledgement, fix or disclosure deadline. We coordinate
disclosure with reporters according to impact, available mitigations and fix
readiness, and communicate an expected schedule when one can reasonably be given.
The private reporting channel remains the starting point for that coordination.

## Execution boundary

Apizr generation must not execute supplied Python or notebook code. Importing
or running a generated application **does execute its source module**. Only run
code you trust in an environment appropriate to its privileges. Local-process execution does not isolate host filesystem or network access. OCI
execution adds Linux container controls with a trusted Docker host and worker image;
it is not a VM boundary. Both execution backends remain experimental and require
trusted code. Static `READY` does not mean runtime safe. Upload validation is not
a substitute for trusted execution.

## SDK, providers, editors and privacy (Apizr 0.4.6)

The tracking SDK observes trusted code already running in your process. It does
not isolate that workload. Only explicitly selected finite values and files are
recorded; objects are never pickled or traversed to fabricate evidence. Session
authority belongs to one thread/async task. Publication binds the complete Plan
and Run, preserves business exceptions and releases context on interruption.

Static recognition never executes inspected source. Explicitly selected external
providers are trusted installed code invoked through the bounded extension
protocol. Their candidates remain subject to core identity, digest, capability,
location and result-budget validation. Disabled, missing or failed owners yield
unknown evidence without fallback. History reads retained provenance without
loading its producer; a provider has no evidence-store publication authority.

VS Code Restricted Mode starts no Apizr engine. Trusted workspaces still require
explicit engine selection and operator grants before source or history access.
Unsaved buffers do not silently replace saved evidence. The extension launches
bounded engine processes and implements no independent scientific inference.

Telemetry and experiment evidence have separate contracts. Parameters, metric
values/names, paths, source, identifiers and traces never enter usage payloads.
Collection requires explicit consent and remains process-local; production
transmission is unavailable even after opt-in. The qualification guard observes
real CLI/SDK and extension-launched Python processes, denies DNS/INET operations
and asserts zero attempts with collection disabled. Its positive controls prove
that attempts are detected. This is Python audit instrumentation for trusted
qualification workloads; it does not constrain arbitrary native code or VS Code's
own Electron services.

Original 0.4.5 Plan/Run bytes, canonical show/export and comparison remain
readable without a store rewrite. New v2 records are not a promise of backward
reading by 0.4.5. See the [migration guide](docs/releases/migrate-0.4.6.md) and
[retained trust-boundary evidence](review/journey-trust-0.4.6/README.md).

## Automated checks

GitHub default CodeQL setup analyzes Python, JavaScript/TypeScript (including the
VS Code extension) and Actions and publishes alerts on the default and protected
branches and their pull requests. The required `codeql` check reuses those native
analyses: it requires all three successful analyses for the exact commit/ref,
rejects stale or failed evidence, and retains their source-bound SARIF reports.
It starts no duplicate scan on those refs. Unprotected development branches and
tags keep an explicit three-language scan with retained SARIF and no second
public upload. Disabling native setup or removing a language fails the gate.
The dependency job exports the resolved `uv.lock` graph
to temporary PEP 751 lockfiles and audits each with pip-audit. Output distinguishes
runtime, development, documentation and security-tooling dependencies. Every
scope is blocking; all locked variants remain covered.
Findings are not silently ignored. Review the architecture hardening record for
known findings and the limits of locally executed checks.

The VS Code qualification audits its complete locked Node development tree with
no dependency exclusions, verifies exact licence/notice hashes against
`policy/vscode-dependencies.json`, and packages no runtime npm dependency or Python
engine. Usage telemetry is off by default, bounded to process-local counters after
explicit consent, and has no sender. Production transmission remains unavailable
pending the private collector qualification and a subsequent release.
