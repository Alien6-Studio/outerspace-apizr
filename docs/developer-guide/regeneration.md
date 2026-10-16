# Regenerate safely

Update an interface without overwriting a reviewed bundle or losing client edits.
The result is a separately generated candidate you can compare and verify before
changing the service your consumers use.

## Before you begin

Retain the old bundle, input policies and selected source/resources. Know its
runtime requirements and current public operations. Use a trusted output location
with physical paths; symlinked output components are refused.

## Generate to a new directory

Use the same selection and authority with a new output directory, for example
`../bundles/rest-next` instead of `../bundles/rest`. The quote example's build
commands accept this deliberate output change. There is no destructive `--force`
replacement. Generation uses retained source evidence and does not start a server.

Compare public routes, input schemas and application pins. A logical capability ID
can remain unchanged while source and bundle digests change. Preserve the bundle
manifest with the exact bytes you reviewed; do not reformat evidence before hashing.
The [external governance reference](../reference/external-governance.md) explains
export/verification against independently selected identities.

## Verify behavior before switching

Start the candidate on a different local port. Repeat the valid order and invalid
payload tests using the candidate runtime. Stop it if the contract or response is
unexpected. Only then apply your host/container deployment's documented update
procedure; Apizr does not supply a native service rollback command.

For Run-bound services, source/model changes require a new matching successful
Run or exact restoration. Regeneration must not silently reuse a stale model under
an old experiment identity.

## Keep client edits separate

[Client collections](../getting-started/user-guide/client-collections.md) are
exported from verified REST artifacts. `apizr clients sync` manages a wholly
Apizr-owned tree and refuses modified or unknown files. Fork a collection before
hand-editing it; sync is not a merge of your client edits.

For CI, use explicit output directories and artifact retention. `apizr ci` never
cleans previous output or implicitly uploads source. Its overall readiness check
can refuse an unfinished repository even when a separate selected exposure would
succeed. See [CI integration](../getting-started/user-guide/ci-integrations.md).
