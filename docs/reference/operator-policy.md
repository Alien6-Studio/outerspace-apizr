# Authorize an OCI publication

!!! warning "0.4 development — explicit policy now required"
    Managed `apizr-oci push` and `apizr-attest publish` calls require
    `--operator-policy`. An installed, active plugin alone no longer permits
    publication. This changes development commands, not the published 0.3.0 CLI.

Installation puts verified wheel bytes in an isolated environment. Activation
chooses one installed version. **Authorization** permits a particular installed
build to perform one operation on one remote repository. None implies the next.

## Write the operator's policy

Download the complete [operator.json example](../examples/operator.json). It
contains both publication grants and their dependency identities. Its repeated
SHA-256 values are illustrative: they deliberately do not authorize your installed
wheels. Replace every identity with your reviewed installation's metadata.
`lock_sha256` identifies the installation requirements lock; `dependencies` must
contain the entire installed closure with exact versions and SHA-256 values.
For a dependency-free installation, explicitly use `null` and `[]` respectively.
The official publishers currently have dependencies.

To author a complete policy using actual installed identities, first install and
activate the plugins using the [local extension guide](local-extensions.md).
Review their origin and wheel hashes. Run these commands in a directory you
control; choose your actual registry and repository in the Python block:

```sh
apizr plugins list --active --json > installed.json
python3 - <<'PY'
import json
from pathlib import Path

records = json.loads(Path("installed.json").read_text())["installations"]
repository = "registry.example:5443/team/service"
grants = []
for name, operation in (("apizr-oci", "push"), ("apizr-attest", "publish")):
    record = next(item for item in records if item["name"] == name)
    identity = {key: record[key] for key in (
        "name", "version", "sha256", "lock_sha256", "dependencies"
    )}
    grants.append({
        "plugin": identity,
        "operation": operation,
        "repository": repository,
        "permissions": ["registry.read", "registry.publish"],
    })
with Path("operator.json").open("x") as output:
    json.dump({"schema": "apizr.operator-policy/v1", "grants": grants}, output, indent=2)
    output.write("\n")
PY
```

Use the same explicit `--plugins-dir` or `--user-config` for inventory and calls
if you use a nondefault store. Inspect the resulting file before using it. Reading
the inventory supplies identities; this explicit authoring step supplies permission.
Do not obtain the policy from the project being analyzed. Keep it under operator
control, outside project-controlled inputs. There is no policy discovery or
`APIZR_OPERATOR_POLICY` environment variable. `apizr.toml`, catalogs, profiles and
operation arguments cannot select or extend a policy.

The JSON document must specify `schema: apizr.operator-policy/v1` and `grants`.
Files are regular, nonsymlink UTF-8 JSON, at most 65,536 bytes and 128 grants.
Unknown fields/versions, duplicate JSON keys, duplicate dependency names or
permissions, and invalid types are refused. Each grant has exactly:

| Field | Meaning |
| --- | --- |
| `plugin` | Canonical distribution name, exact version, primary wheel `sha256`, `lock_sha256`, full `dependencies` array |
| `operation` | `push` for apizr-oci or `publish` for apizr-attest |
| `repository` | Exact registry, optional explicit port, namespace and image repository; no tag, digest or wildcard |
| `permissions` | Both `registry.read` and `registry.publish` for this operation |

A rebuilt wheel with the same name/version, or a changed lock/dependency set,
needs a new grant. Reordering dependencies does not change identity. A grant must
contain both required permissions; separate partial grants are not combined.
No grant contains credentials, a private key or a free-form command.

## Publish the selected image and its proof

Prepare [push.json](oci-service-plugin.md#publish-a-verified-service-image) with the
immutable local image ID, expected platform/input digest and explicit Docker/auth
configuration. Prepare [publish.json](attest-oci-artifacts.md) with the already
signed proof, image digest, public trust and native verification tools.

```sh
apizr plugins run apizr-oci push --arguments push.json \
  --operator-policy operator.json --timeout-ms 360000
apizr plugins run apizr-attest publish --arguments publish.json \
  --operator-policy operator.json --timeout-ms 360000
```

The core validates the active installation and acquires its existing usage
protection. It snapshots the arguments, validates the shared publication contract,
and decides before starting a plugin, contacting Docker/a registry or reading
registry credentials. The plugin receives the same checked argument snapshot;
changing the original file or Python dictionary cannot substitute a destination.
Authorization does not replace activation, identity, usage, TLS, image/proof
verification or registry access checks. Existing interruption and unconfirmed
remote-state behavior is unchanged.

Successful calls return the existing plugin response. Keep the image
`digest_reference` from push and `artifact_reference` from proof publication.
Publishing an already signed proof verifies it; it requires no private key and
no new signature permission.

## Match the destination exactly

For `registry.example:5443/team/service:v1`, the authorized repository is
`registry.example:5443/team/service`. The same grant covers other explicit tags
and SHA-256 digests in that repository, not another port, registry, path or
`service-other`. Short Docker Hub names such as `alpine` or `team/service` remain
ambiguous and are refused; use `docker.io/library/alpine:tag` or an explicit
namespace. The existing `index.docker.io` alias normalizes to `docker.io`.
Other host spellings and explicit ports retain separate identities. Credentials,
URL schemes, percent encodings, traversal and wildcards are not accepted.

Both operations read remote state before and after writing, so read-only access
is insufficient. Push's temporary `apizr-upload-*` tag stays in the **same**
repository. Attest attaches the proof to the requested image digest in that same
repository. Neither step implicitly grants access to a second repository.

## Call from Python and handle decisions

```python
from pathlib import Path
from apizr.extension_runtime import Limits
from apizr.local_plugins import read_arguments, run_extension
from apizr.operator_policy import AuthorizationDenied, load_operator_policy

try:
    response = run_extension(
        "apizr-oci",
        "push",
        read_arguments(Path("push.json")),
        operator_policy=load_operator_policy(Path("operator.json")),
        limits=Limits(wall_time_ms=360000),
    )
except AuthorizationDenied as error:
    print(error.decision.model_dump_json(by_alias=True))
else:
    print(response.model_dump_json())
```

`decide(policy, installation, operation, arguments)` is the typed, pure decision
API: no file, process, Docker or network access. It returns
`apizr.operator-decision/v1`, an `allowed` boolean and a fixed `code`. It alone
does not authenticate an installation; use `run_extension` for managed execution.
Loading the explicitly chosen file is a separate operation.

CLI authorization failures exit **2**, leave stdout empty and write that JSON
decision to stderr. Python raises `AuthorizationDenied` with the same decision.
No paths, reference values, credentials or native diagnostics appear in it.

| Code | Decision |
| --- | --- |
| `authorized` | This publication matches a complete grant |
| `not_required` | This operation is outside this first authorization scope |
| `operator_policy_required` | No policy was supplied |
| `operator_policy_invalid` / `operator_policy_unavailable` / `operator_policy_too_large` | Policy refused before invocation |
| `operator_arguments_invalid` | Publication arguments do not satisfy the shared contract |
| `operator_identity_denied` | Installed build/closure or official entry point does not match |
| `operator_operation_denied` | No matching operation grant |
| `operator_repository_denied` | No matching exact repository |
| `operator_permissions_denied` | The grant lacks a required registry permission |

## Understand the boundary

This is admission control for **managed Apizr invocations**, not a sandbox against
a malicious trusted plugin. Directly invoking a plugin, Docker/ORAS/Attest or the
low-level `extension_runtime.invoke_extension` outside the managed installation
path does not acquire operator authorization. Protect operator files and plugin
storage from untrusted writers; plugins still execute with the user's rights.

This pass covers only image `push` and proof `publish`. Git access, analysis,
construction, signing and the other operations retain their existing controls;
`not_required` does not claim they have completed operator authorization.
`build`, `attest`, `verify`, plugin lifecycle/catalog operations and the analysis
MCP server keep their behavior. Publication through MCP is not added.
