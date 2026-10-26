# Client-collection qualification dependencies

These are development/CI tools, not Apizr runtime dependencies. Use Node
**22.22.2** (the native CI version) and the committed lock:

```sh
npm ci --prefix scripts/client_collection_tools --ignore-scripts --no-audit --no-fund
npm audit --prefix scripts/client_collection_tools --json --include=prod --include=dev --include=optional --include=peer --audit-level=moderate
node scripts/client_collection_tools/check-compatibility.cjs
```

The protected Security `dependencies` job runs this real audit and retains
`node-dependency-audit.json` alongside the Python evidence. Moderate, high and
critical findings or audit service errors fail qualification. No advisory is
ignored and no dependency category is omitted. `--no-audit` on installation only
separates installation from the explicit, blocking audit. Lifecycle scripts are
never enabled. The client-collection workflow separately validates generated
Postman, Bruno/OpenCollection and Insomnia collections and executes their real
requests outside the checkout after deleting the original source.

## Reviewed security overrides — 2026-10-11

Tracking: [#280](https://github.com/Alien6-Studio/outerspace-apizr/issues/280).
Direct upgrades are Bruno **4.2.0 → 4.2.1** and Postman **1.67.0 → 1.73.0**;
OpenCollection schema **0.14.0** remains the current release. Re-resolving the
current direct graph fixes Handlebars at **4.7.10** without an override. Bruno's
published manifests still prevent the remaining corrected versions from being
selected. `package.json` scopes each exception to those exact parent versions;
a future parent upgrade must review/remove the exception, not silently inherit it.

| Package | Original → corrected | Constraint requiring an override | Compatibility reviewed |
| --- | --- | --- | --- |
| axios | 1.18.0 → 1.20.0 | Exact pins in CLI, JS and requests | Same major; actual HTTP request, response and JSON behavior exercised by all native collection executions |
| form-data | 4.0.4 → 4.0.6 | Exact CLI pin | Same major; multipart construction/header API checked; generated requests remain JSON |
| js-yaml | 4.3.1 → 4.3.2 | Exact CLI/converters pins | Patch correction; YAML round-trip and real collection parsing |
| yaml | 2.3.4 → 2.8.3 | Exact filestore/JS pins | Same major; YAML round-trip and real OpenCollection import |
| csv-parse | 5.6.0 → 7.0.2 | CLI `^5.5.6` | Retains CommonJS `parse` callback API and used options; test invokes Bruno's actual `parseCSV` with BOM, quoted Unicode, trimming and empty lines |
| uuid | 10.0.0 → 11.1.1 | JS `^10.0.0` | CommonJS remains supported in 11; Bruno uses `v4()` and exposes supported UUID functions; generation, parsing, v5 and buffer refusal checked |
| @faker-js/faker | 9.9.0 → 10.5.0 | requests `^9.7.0` | v10 requires Node 20.19+/22.13+ for CommonJS/ESM interop; pinned Node 22.22.2 qualifies it; Bruno's number/boolean/word/alpha call shapes exercised |

The CSV/Faker/UUID major changes are limited to the actual APIs used by this
qualification tooling. This is not a compatibility claim for every third-party
Bruno plugin, arbitrary user script or generated random sequence. Runtime
contracts of Apizr and its generated services do not depend on these packages.
Overrides cannot fix code embedded in upstream prebuilt bundles; the audit
establishes the safety of the installed dependency graph against current
advisories, not an independent audit of every vendor binary or bundled source.

Primary sources inspected on 2026-10-11:

- [npm audit semantics](https://docs.npmjs.com/cli/v11/commands/npm-audit/):
  audit level affects exit status, not which findings are reported.
- Published npm manifests for `@usebruno/cli@4.2.1`, `@usebruno/js@0.54.0`,
  `@usebruno/requests@0.21.0`, `@usebruno/converters@0.24.0` and
  `@usebruno/filestore@0.13.0`, plus their installed vendor call sites.
- [Faker v10 migration](https://fakerjs.dev/guide/upgrading) and
  [UUID changelog](https://github.com/uuidjs/uuid/blob/main/CHANGELOG.md).
- Published `csv-parse@7.0.2` exports/types and Bruno's
  `src/utils/filesystem.js` callback parser.

The issue retains every initial GHSA, installed version, dependency path,
fixed version and reachability assessment. Initial Dependabot had 18 alerts
(10 high, 8 moderate); the real npm audit also found three Handlebars advisories,
including two critical. npm's 13 affected-package count includes parent
metavulnerabilities and must not be confused with an advisory count. Even a
vulnerable feature unused by the current fixture blocks the release; there is
no development-tooling exemption.

## Security refresh — 2026-10-26

The lock updates `fast-uri` **3.1.8 → 3.1.9**, `ip-address`
**10.7.3 → 10.7.5** and `undici` **7.30.0 → 7.30.1** within their existing
parent constraints. Azure Identity **4.13.3** still requires MSAL Node `^6.0.0`,
so an override scoped to that exact parent selects **7.1.1**, which includes the
[authorization-code security correction](https://github.com/AzureAD/microsoft-authentication-library-for-js/releases/tag/msal-node-v7.1.0).
Remove or review that override when Azure Identity changes.

MSAL 7 removes the interactive `responseMode` option. The installed Azure
Identity adapter does not supply that option. The compatibility check exercises
Azure Identity's actual client-secret adapter through MSAL 7, with discovery and
token responses supplied in memory. This verifies request parameters and token
handling without Azure credentials; it does not qualify every Azure credential
or interactive browser flow. The full npm audit reports zero vulnerabilities
across all dependency categories. Dependabot now monitors this npm directory.
