# Foundation dependency audit

Recorded 2026-09-20. The audit exits **1**; the security gate is intentionally
blocking. No advisories are ignored and no findings are automatically fixed.

The command exports the actual universal `uv.lock` with all dependency groups
to PEP 751 and passes that lockfile to pip-audit 2.10.1. The auditor checks every
locked package/version variant, including versions used only on older Python
or other operating systems. It does not filter to the audit host's environment.
The local editable project is omitted because it is the code under analysis,
not an external dependency.

The audit examined **243 package/version entries** and reported findings in **29 entries across 18 packages**: **79 distinct package/version/advisory combinations** after deduplicating repeated advisory IDs. Aliases can still describe the same underlying vulnerability.

## Compatibility constraints

The newest compatible versions in the lock still include older releases for
Python 3.8 and 3.9. PyPI metadata for the listed fixed releases requires newer
Python versions. Resolving all findings would require a support-policy change,
upstream backports or a separately reviewed replacement; this PR does none of
those. The table records the newest fix listed across each package's findings,
not a promise that updating that one package resolves the complete graph.
Some entries are development or documentation dependencies, not runtime code.
The audit includes those intentionally. Exploitability in Apizr has not been
established by the dependency scanner.

| Package | Affected locked versions | Latest listed fix | Fix requires Python |
| --- | --- | --- | --- |
| anyio | 4.5.2, 4.12.1 | [4.14.2](https://pypi.org/pypi/anyio/4.14.2/json) | `>=3.10` |
| black | 24.8.0, 25.11.0 | [26.3.1](https://pypi.org/pypi/black/26.3.1/json) | `>=3.10` |
| bleach | 6.1.0, 6.2.0 | [6.4.0](https://pypi.org/pypi/bleach/6.4.0/json) | `>=3.10` |
| click | 8.1.8 | [8.3.3](https://pypi.org/pypi/click/8.3.3/json) | `>=3.10` |
| filelock | 3.16.1, 3.19.1 | [3.20.3](https://pypi.org/pypi/filelock/3.20.3/json) | `>=3.10` |
| markdown | 3.7 | [3.8.1](https://pypi.org/pypi/markdown/3.8.1/json) | `>=3.9` |
| nbconvert | 7.16.6 | [7.17.1](https://pypi.org/pypi/nbconvert/7.17.1/json) | `>=3.9` |
| pygments | 2.19.2 | [2.20.0](https://pypi.org/pypi/pygments/2.20.0/json) | `>=3.9` |
| pymdown-extensions | 10.15, 10.21.3 | [11.0.1](https://pypi.org/pypi/pymdown-extensions/11.0.1/json) | `>=3.10` |
| pytest | 8.3.5, 8.4.2 | [9.0.3](https://pypi.org/pypi/pytest/9.0.3/json) | `>=3.10` |
| python-dotenv | 1.0.1, 1.2.1 | [1.2.2](https://pypi.org/pypi/python-dotenv/1.2.2/json) | `>=3.10` |
| python-multipart | 0.0.20 | [0.0.31](https://pypi.org/pypi/python-multipart/0.0.31/json) | `>=3.10` |
| requests | 2.32.4, 2.32.5 | [2.33.0](https://pypi.org/pypi/requests/2.33.0/json) | `>=3.10` |
| soupsieve | 2.7, 2.8.4 | [2.9.0](https://pypi.org/pypi/soupsieve/2.9.0/json) | `>=3.10` |
| starlette | 0.44.0, 0.49.3 | [1.3.1](https://pypi.org/pypi/starlette/1.3.1/json) | `>=3.10` |
| tornado | 6.4.2 | [6.5.8](https://pypi.org/pypi/tornado/6.5.8/json) | `>=3.9` |
| urllib3 | 2.2.3, 2.6.3 | [2.7.0](https://pypi.org/pypi/urllib3/2.7.0/json) | `>=3.10` |
| wheel | 0.45.1 | [0.46.2](https://pypi.org/pypi/wheel/0.46.2/json) | `>=3.9` |

## Findings by locked version

- **anyio 4.5.2**: `CVE-2026-63374`, `CVE-2026-64847`.
- **anyio 4.12.1**: `CVE-2026-63374`, `CVE-2026-64847`.
- **black 24.8.0**: `PYSEC-2026-2120`, `PYSEC-2026-2121`.
- **black 25.11.0**: `PYSEC-2026-2120`, `PYSEC-2026-2121`.
- **bleach 6.1.0**: `GHSA-8rfp-98v4-mmr6`, `GHSA-gj48-438w-jh9v`.
- **bleach 6.2.0**: `GHSA-8rfp-98v4-mmr6`, `GHSA-gj48-438w-jh9v`.
- **click 8.1.8**: `PYSEC-2026-2132`.
- **filelock 3.16.1**: `PYSEC-2026-1374`, `PYSEC-2026-1375`.
- **filelock 3.19.1**: `PYSEC-2026-1374`, `PYSEC-2026-1375`.
- **markdown 3.7**: `PYSEC-2026-89`.
- **nbconvert 7.16.6**: `PYSEC-2026-1691`, `PYSEC-2026-2229`, `PYSEC-2026-2230`.
- **pygments 2.19.2**: `PYSEC-2026-2987`.
- **pymdown-extensions 10.15**: `PYSEC-2026-1825`, `PYSEC-2026-2999`, `PYSEC-2026-3609`, `PYSEC-2026-3654`.
- **pymdown-extensions 10.21.3**: `PYSEC-2026-3609`, `PYSEC-2026-3654`.
- **pytest 8.3.5**: `PYSEC-2026-1845`.
- **pytest 8.4.2**: `PYSEC-2026-1845`.
- **python-dotenv 1.0.1**: `PYSEC-2026-2270`.
- **python-dotenv 1.2.1**: `PYSEC-2026-2270`.
- **python-multipart 0.0.20**: `PYSEC-2026-1852`, `PYSEC-2026-3036`, `PYSEC-2026-3037`, `PYSEC-2026-3038`, `PYSEC-2026-3039`, `PYSEC-2026-3040`.
- **requests 2.32.4**: `PYSEC-2026-2275`.
- **requests 2.32.5**: `PYSEC-2026-2275`.
- **soupsieve 2.7**: `CVE-2026-85999`, `CVE-2026-86000`, `PYSEC-2026-3071`, `PYSEC-2026-3072`.
- **soupsieve 2.8.4**: `CVE-2026-85999`, `CVE-2026-86000`.
- **starlette 0.44.0**: `PYSEC-2026-161`, `PYSEC-2026-1941`, `PYSEC-2026-1942`, `PYSEC-2026-2280`, `PYSEC-2026-2281`, `PYSEC-2026-248`, `PYSEC-2026-249`.
- **starlette 0.49.3**: `PYSEC-2026-161`, `PYSEC-2026-2280`, `PYSEC-2026-2281`, `PYSEC-2026-248`, `PYSEC-2026-249`.
- **tornado 6.4.2**: `GHSA-8423-8fgw-73vq`, `GHSA-pw6j-qg29-8w7f`, `PYSEC-2025-265`, `PYSEC-2025-266`, `PYSEC-2025-267`, `PYSEC-2026-140`, `PYSEC-2026-1974`, `PYSEC-2026-2287`, `PYSEC-2026-3387`, `PYSEC-2026-3388`, `PYSEC-2026-3389`, `PYSEC-2026-3928`.
- **urllib3 2.2.3**: `PYSEC-2026-141`, `PYSEC-2026-1994`, `PYSEC-2026-1996`, `PYSEC-2026-1997`, `PYSEC-2026-1998`, `PYSEC-2026-1999`.
- **urllib3 2.6.3**: `PYSEC-2026-141`, `PYSEC-2026-142`.
- **wheel 0.45.1**: `CVE-2026-24049`.

## Reproduce

```bash
uv sync --locked --group security
uv run --locked --group security python scripts/audit_dependencies.py
# Optional full descriptions, aliases and fix versions:
uv run --locked --group security python scripts/audit_dependencies.py --output /tmp/apizr-audit.json
```

Database results may change. The private reporting channel and execution
boundary are documented in [SECURITY.md](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/SECURITY.md).
CodeQL is configured separately and must run in GitHub Actions; adding its
workflow does not establish that analysis has passed.
