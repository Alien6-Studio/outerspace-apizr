# Security policy

## Supported versions

Security fixes target the current 0.2.x line. Apizr and generated targets support
**Python 3.11–3.14**. Use a supported interpreter and keep dependencies updated.
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

## Execution boundary

Apizr generation must not execute supplied Python or notebook code. Importing
or running a generated application **does execute its source module**. Only run
code you trust in an environment appropriate to its privileges. Local-process execution does not isolate host filesystem or network access. OCI
execution adds Linux container controls with a trusted Docker host and worker image;
it is not a VM boundary. Both execution backends remain experimental and require
trusted code. Static `READY` does not mean runtime safe. Upload validation is not
a substitute for trusted execution.

## Automated checks

GitHub default CodeQL setup analyzes Python and Actions and publishes alerts.
The explicit Python workflow also retains its SARIF report as an artifact; it
does not upload a second copy while default setup is enabled. The dependency job exports the resolved `uv.lock` graph
to temporary PEP 751 lockfiles and audits each with pip-audit. Output distinguishes
runtime, development, documentation and security-tooling dependencies. Every
scope is blocking; all locked variants remain covered.
Findings are not silently ignored. Review the architecture hardening record for
known findings and the limits of locally executed checks.
