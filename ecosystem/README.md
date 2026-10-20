# Public ecosystem maintenance

Audit date: **20 October 2026**. Reference: **0.4.6**, published on 19 October.
This inventory covers the requested platforms, the four coordinated Python
packages and two additional package indexes. It does not claim exhaustive
coverage of the internet.

The retained audit records **15 confirmed listings, 9 obsolete listings,
3 scoped absences and 2 indeterminate searches**. See the
[full report](reports/2026-10-20/report.md) and
[machine-readable report](reports/2026-10-20/report.json).

| Finding | Evidence and next action |
| --- | --- |
| Current 0.4.6 | Official MCP Registry, four PyPI packages, Tracevero, VS Code Marketplace, official Homebrew tap, four Safety pages, Libraries.io, deps.dev and GitHub release. |
| Glama inspection is old | Its README shows 0.4.6, but the inspected surface and 2 October assessment cover three tools. Request reinspection of all six default tools; keep the old score dated. |
| Arcade evaluates the wrong surface | Its 23 September assessment treats seven legacy HTTP endpoints as MCP tools. Request a new assessment of the local stdio plugin. |
| Version ingestion lags | MCPLookup, Socketlist and four piwheels records still show 0.4.5. Request refresh if normal post-release ingestion does not resolve this. |
| Nowfound retains historical positioning | The 2023 launch describes notebook-to-FastAPI generation. Prepare a current product summary while preserving launch history. |
| Scoped absence | MCP.so and PulseMCP explicitly return zero results for both package and spaced product names. The Homebrew core API returns 404 for the exact `apizr` Formula; the official tap exists. These checks do not exclude unknown aliases. |
| Indeterminate | Smithery's documented semantic search returns non-matching candidates on page one; it is not an exhaustive catalogue check. LobeHub's retrieved landing page does not establish search results. |

No third-party correction was submitted, account created, package published,
Registry record replaced, tap changed or Marketplace extension republished.
The [correction drafts](correction-requests.md) contain the remaining publisher
actions. PulseMCP currently announces a pause on submissions and listing changes.

## Sources and ownership

- [registry-audit.json](registry-audit.json): versioned inventory, exact listing
  and probe URLs, verification dates, features, editorial status, scores and
  platform-specific update procedures. JSON keeps the independent checker on
  the Python standard library; it adds no product dependency.
- [canonical-descriptions.json](canonical-descriptions.json): international
  English product copy in short (134 characters), standard (451 characters) and
  detailed forms, plus analysis-server copy. The dedicated Registry variant is
  94 characters, within its stricter 100-character schema limit.
- [publication-baseline.json](publication-baseline.json): original published
  summaries, distribution URLs/hashes, release source, tagged source hashes and
  website revision. This captures public metadata; it does not re-download and
  requalify every release archive.
- [evidence/2026-10-20.json](evidence/2026-10-20.json): dated observations extracted
  from direct public responses, including response hashes. Supporting searches
  and update/API documentation are recorded in
  [supporting-2026-10-20.json](evidence/supporting-2026-10-20.json).
- [verify.py](verify.py): independent read-only maintenance tool, deliberately
  outside `src/apizr` and the release qualification scripts.

The current branch updates the product and MCP package summaries, root README,
plugin README and `server.json`. These are source changes for review and a future
authorised publication. They do not change already uploaded 0.4.6 metadata.
`glama.json` already declares maintainer `Coopyrightdmin`; no schema-unsupported
description field was added there.

Website sources remain on **`gh-pages`**, whose README and public MCP guide were
checked. No `docs/` tree was recreated on the product branch. The current public
guide already documents the six default tools and separate delivery permissions,
so it needs no correction for this audit. VS Code source belongs to the separate
`outerspace-apizr-vscode` repository; the published tap belongs to `homebrew-tap`.
Their snapshots and release pins remain intact.

## Reproduce the reports

Python 3.11 or later is sufficient; no package installation is needed.

```sh
python3 -m unittest discover -s tests/ecosystem -v
python3 ecosystem/verify.py \
  --replay ecosystem/evidence/2026-10-20.json \
  --as-of 2026-10-20T12:09:00+00:00 \
  --output /tmp/apizr-ecosystem-replay
```

That command deterministically regenerates `observations.json`, `report.json`
and `report.md` from the retained observations. It does not refetch or reconstruct
the original pages. Response hashes identify the original responses; the
repository retains extracted facts rather than full third-party HTML. Parser
tests use synthetic local HTTP fixtures, including malformed responses and
explicit negative results.

For a current check of the documented public APIs:

```sh
python3 ecosystem/verify.py --live --output /tmp/apizr-ecosystem-current
```

For an occasional manual check that also revisits the reviewed HTML URLs:

```sh
python3 ecosystem/verify.py --live --include-manual \
  --output /tmp/apizr-ecosystem-manual
```

Live mode observes `robots.txt`, fails closed if its access policy cannot be
checked, uses an identified user agent, a ten-second socket timeout, a two-MB
response limit, at least two seconds between requests to a host, and any larger
declared crawl delay/request interval. Long delays are deferred. It follows only
reviewed HTTPS origins, uses no credentials and does not retry failures or
rate-limit responses. It does not bypass access challenges. HTML is an explicit
best-effort fallback where an unauthenticated documented API is unavailable.
Glama's directory API requires a publisher-provided key; no key was created.
Operators should review platform terms before enabling additional automation.

The [retained live run](reports/2026-10-20-live/report.md) independently confirmed
three current API records and detected four piwheels version mismatches. The
other 22 entries remain indeterminate in this automated run: 17 are intentionally
manual-only, while the four PyPI JSON endpoints and deps.dev were deferred by
their captured `robots.txt` policies. These automated limitations do not erase
the separately dated direct audit observations. A catalogue becoming inaccessible
must not be reported as a disappearance or a successful current version check.

`--fixtures DIRECTORY` reads raw HTTP response fixtures named after listing IDs
instead of making requests. Missing fixtures produce unknown observations.
`--replay FILE` consumes already extracted observations. Both modes make no
network requests. Use `--inventory FILE` for a smaller fixture inventory.

## Interpret and maintain the inventory

`confirmed` requires identity evidence. Its version may still be unknown.
`obsolete` means the captured version differs from the reference or the observed
surface contains an identified presentation error. A newer version also produces
a mismatch: maintainers must review the fixed audit reference rather than assume
every mismatch is a downgrade. `absent_confirmed` requires an explicit platform
negative result or an exact authoritative lookup configured for that purpose.
`indeterminate` covers incomplete results, access failures and unrecognised pages.
Search-engine snippets were used for discovery only.

The checker keeps three separate clocks: current response capture, last editorial
review, and the platform's own assessment date. Observations older than 14 days
cannot establish a current version/status. Future-dated evidence also cannot
pass. A fresh page does not make its old quality score fresh, and an unknown
assessment date remains unknown. Failed live checks preserve the dated editorial
review without promoting its version into current verified evidence.

After each substantive manual review, update the entry's `review` fields and
supporting URLs, retain a new dated evidence snapshot, then generate a new dated
report directory. Do not overwrite historical snapshots. Update `reference_version`
deliberately when a later stable release becomes the audit baseline. Review
capability descriptions and tool names against that release as well.

Normal report generation exits zero even when drift or uncertainty is found.
Opt-in `--strict` exits 1 for drift/scoped absence, or 2 for incomplete/stale
evidence; incomplete evidence takes precedence. This is intended for manual
maintenance decisions, not release admission.

The offline tests are also collected by the repository's existing PR test suite.
The independent [GitHub workflow](../.github/workflows/ecosystem-registry.yml)
checks public APIs each Tuesday at 07:23 UTC, with manual dispatch available.
It uploads reports for 90 days and
writes the live report to its job summary. It has read-only repository permission,
no secrets, no external submissions and no publishing steps. It adds no dependency
from a core qualification or publication job to network catalogue availability.
The schedule becomes active only after the workflow reaches the default branch.
