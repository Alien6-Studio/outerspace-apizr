# Security policy

## Supported versions

Security fixes target the current 0.2.x line. The historical 0.1.x line is not
maintained. Apizr's advertised Python compatibility remains 3.8–3.14; this does
not extend upstream Python or dependency security support. Some older Python
interpreters require older dependency versions. Review the dependency audit
before deploying; compatibility is not a guarantee of vulnerability-free code.

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
code you trust in an environment appropriate to its privileges. Apizr provides
no runtime sandbox. Upload validation is not a substitute for trusted execution.

## Automated checks

GitHub default CodeQL setup analyzes Python and Actions and publishes alerts.
The explicit Python workflow also retains its SARIF report as an artifact; it
does not upload a second copy while default setup is enabled. The dependency job exports the resolved `uv.lock` graph
to a temporary PEP 751 lockfile and audits it with pip-audit, including alternate
versions for supported Python targets and development/documentation tools.
Findings are not silently ignored. Review the architecture hardening record for
known findings and the limits of locally executed checks.
