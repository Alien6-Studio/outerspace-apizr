# Client collections

The **0.4.2rc2 version under qualification** generates local Postman, Bruno
and Insomnia collections from an existing Apizr REST bundle:

```text
Python → Apizr REST bundle → client collection
```

First produce the bundle using [repository exposure](exposure.md) or the
[single-source REST workflow](rest.md). Collection generation verifies retained
artifacts; it does not rescan, import or execute the original project.

Install the optional `clients` extra from the matching development wheel, or use
`uv sync --extra clients` in the development checkout. The extra supplies PyYAML;
the minimal core still requires only Pydantic. Apizr does not install client apps.

## Export

```sh
apizr clients export --bundle .output/rest --format postman --output-dir .output/postman
apizr clients export --bundle .output/rest --format bruno --output-dir .output/bruno
apizr clients export --bundle .output/rest --format insomnia --output-dir .output/insomnia
```

The parent directory must already exist. The output directory must be absent or
empty. Relative and absolute paths are supported; symlink traversal is refused.
Output is prepared in a sibling staging directory before publication.

Use `--base-url https://api.example.test` to select the server explicitly. The
default is `http://127.0.0.1:8000`; each format uses a `base_url` variable.
Only HTTP(S) URLs without credentials, query strings, fragments or control
characters are accepted. `--name` defaults to `Apizr REST API`.

Each exposed capability produces one POST request with a JSON body and
`Content-Type: application/json`. No authentication, cookies, scripts, tests or
secrets are generated. Required arguments receive minimal deterministic values:
zero, empty string, false, null, empty containers, fixed tuple members, the first
literal or the first union member. Optional arguments are omitted so Python
defaults remain in effect. Return schemas describe the existing REST contract;
they do not introduce response enforcement or fabricated response examples.

## Native formats

| Format | Output | Official validation used |
| --- | --- | --- |
| Postman Collection 3.0.0 | `.resources/definition.yaml` and one `*.request.yaml` per capability | Postman CLI 1.67.0 lint and local execution |
| Bruno OpenCollection 1.0.0 | `opencollection.yml` and one request `.yml` per capability | `@opencollection/schema` 0.14.0 and Bruno CLI 4.2.0 |
| Insomnia v5, schema 5.1 | `collection.yaml`, type `collection.insomnia.rest/5.0` | Official JSON Schema and Inso CLI 13.3.0 local execution |

These are the current native formats documented by
[Postman](https://learning.postman.com/docs/use/use-collections/collections-schemas),
[Bruno](https://docs.usebruno.com/opencollection-yaml/overview) and
[Insomnia](https://developer.konghq.com/insomnia/import-export/).
The qualification tools are development-only, with exact npm versions and
integrity values in `scripts/client_collection_tools/package-lock.json`.
Insomnia's schema is pinned to commit
`ab658aa7e419ff155511370dff3d32d53ae5ea53`, SHA-256
`65b37ac4118a89aa8b15e381e5bafdc7a8580f3c386b6c65b4db8ba04a86fa17`.

Postman 3 local execution supports its CLI reporter, not the JSON reporter used
for older collections. Qualification checks the verbose native responses and
also replays the common IR against the fixture. Postman may print a login notice;
local lint and execution work without an account. Bruno and Inso additionally
provide machine-readable execution results. No cloud API or account is needed.

## Regenerate safely

```sh
apizr clients sync --bundle .output/rest --format postman --output-dir .output/postman
```

`sync` regenerates a fully Apizr-owned local tree. It does not synchronize with a
cloud workspace or import client edits. The previous manifest, retained IR and
all owned file hashes must match. Unknown files, empty extra directories, links,
modified files, missing manifests and a different format cause refusal before
the generated tree changes.

Copy/fork a generated collection before hand-editing it. `apizr clients sync`
manages a generated tree; it is not a merge engine.

The replacement is staged and verified on the same filesystem. The previous
tree is renamed to a backup before the prepared tree takes its place. Caught
interruptions restore the previous tree where publication has not completed.
A crash can leave a sibling `.apizr-clients-<root-name-hash>.stage`, `.backup`
or `.lock`; subsequent commands refuse with `client_sync_conflict`. Preserve
those directories, inspect the manifest and hashes, and recover the previous
backup manually before removing stale staging/lock entries. No automatic retry
or cleanup guesses which interrupted tree to keep.

## Python and portable identities

```python
from apizr.client_collections import (
    plan_client_collection,
    render_client_collection,
    publish_collection,
)

collection = plan_client_collection(".output/rest", base_url="http://127.0.0.1:8000")
files = render_client_collection(collection, format="bruno")
result = publish_collection(collection, format="bruno", output_dir=".output/bruno")
```

`export_client_collection(..., sync=True)` combines planning, rendering and
publication. Pure models and canonical JSON work without YAML installed.
One frozen strict `apizr.client-collection/v1` model supplies every renderer.
Its SHA-256 covers canonical UTF-8 JSON with sorted keys, compact separators
and a final LF. Request ordering follows the REST manifest.

Both `apizr.repository-rest/v1` and historical `apizr.rest/v1` are supported.
Every manifest-declared artifact is read as a bounded regular file and checked
against its recorded digest; unrelated files are not read. OpenAPI must match
the typed endpoint contracts, including routes, methods, identities and schemas.
Repository exports retain interface and exposure-plan digests; single-source
exports retain IR and readiness digests. Manifest hashes establish retained
content identity, not independent signatures or publisher authenticity.

Each output includes `apizr-client-collection.json` and an
`apizr.client-export/v1` manifest, `apizr-client-export.json`. The manifest binds
the collection digest, source REST manifest digest, format/version, explicit
options, capability IDs, generated paths and SHA-256 file hashes. It excludes
timestamps, source paths, usernames, environment and network state.

Insomnia entity IDs use the first 128 bits of SHA-256 over canonical JSON
`[format, collection_digest, capability_id, role]`. Request filenames use a
bounded ASCII slug and the first 64 bits of the capability ID's SHA-256, even
without a collision; this keeps names stable when new requests are added.
Case, Unicode and truncation collisions never silently discard a request.
An actual digest-name collision is refused. All files use deterministic YAML,
UTF-8, LF, stable keys and no aliases.

Limits: 512 requests, 4 MiB per input/generated file, 32 MiB total input/export,
2,048 files, 256 UTF-8 bytes per name/identity, 8 KiB per description, 128 bytes
per generated path component and 512 per relative path. Oversize inputs are
refused without truncation.

CLI stdout is canonical JSON: `apizr.client-export-result/v1` on success, or a
fixed diagnostic on refusal. Exit codes are 0 for success, 1 for changed input
or output ownership conflicts, 2 for invalid/operational input or a missing
`clients` extra, and 130 for cancellation. Diagnostics include
`rest_bundle_invalid`, `rest_bundle_changed`, `client_format_unsupported`,
`client_collection_too_large`, `client_name_invalid`, `client_base_url_invalid`,
`client_path_collision`, `client_output_not_empty`, `client_export_invalid`,
`client_export_modified`, `client_sync_conflict` and `clients_extra_required`.
