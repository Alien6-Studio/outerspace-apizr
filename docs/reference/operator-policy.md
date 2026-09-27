<span id="authorize-an-oci-publication"></span>

# Authorize image builds, signing and publication

!!! warning "0.4 development — explicit policy required"
    Managed `apizr-oci build`, `apizr-oci push`, `apizr-attest publish` and `apizr-attest attest` calls require
    `--operator-policy`. An installed, active plugin alone no longer permits
    building, publication or signing. This changes development commands, not the published 0.3.0 CLI.

Installation puts verified wheel bytes in an isolated environment. Activation
chooses one installed version. **Authorization** permits a particular installed
build to perform one operation on explicitly selected inputs or a remote repository. None implies the next.

## Write the operator's policy

Download the complete [operator.json example](../examples/operator.json). It
contains separate image build, image publication, proof publication and signing grants with
their dependency identities. Its repeated
SHA-256 values are illustrative: they deliberately do not authorize your installed
wheels. Replace every identity with your reviewed installation's metadata.
`lock_sha256` identifies the installation requirements lock; `dependencies` must
contain the entire installed closure with exact versions and SHA-256 values.
For a dependency-free installation, explicitly use `null` and `[]` respectively.
The official publishers currently have dependencies.

To author publication grants using actual installed identities, first install and
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
permissions, and invalid types are refused. Publication grants retain their existing fields and meaning:

| Field | Meaning |
| --- | --- |
| `plugin` | Canonical distribution name, exact version, primary wheel `sha256`, `lock_sha256`, full `dependencies` array |
| `operation` | `push` for apizr-oci or `publish` for apizr-attest |
| `repository` | Exact registry, optional explicit port, namespace and image repository; no tag, digest or wildcard |
| `permissions` | Both `registry.read` and `registry.publish` for this operation |

A rebuilt wheel with the same name/version, or a changed lock/dependency set,
needs a new grant. Reordering dependencies does not change identity. A grant must
contain both required permissions; separate partial grants are not combined.
No grant contains credentials, private key bytes or a free-form command.
Signing grants add explicit references as described below.

## Authorize an image build

Managed `apizr-oci build` requires its own `operation: build` grant. The complete
[operator.json example](../examples/operator.json) includes one REST build rule.
Replace its fictitious plugin and base hashes with reviewed values. To grant MCP
construction too, add a distinct rule with that interface and its exact inputs/tag.
Keep the existing publication and signing rules separate.

Each build grant contains `plugin`, `operation`, `target` and `permissions`.
`plugin` uses the full installed identity and locked closure described above.
Use `apizr plugins list --active --json` to obtain those identities from the same
store used for invocation, then review them and explicitly choose the target.
The `target` object shares the builder's existing input validators:

| Target field | Required match |
| --- | --- |
| `base_image` | Exact base reference pinned by SHA-256 digest |
| `interface`, `platform` | Exact `rest`/`mcp` and `linux/amd64`/`linux/arm64` |
| `bundle`, `requirements`, `wheelhouse` | Exact absolute input references |
| `docker` | Exact executable, socket and optional Buildx path (`null` or omitted means none) |
| `tag` | Exact local output tag |

`permissions` must contain **both** `image.build` and `registry.read` in the same
matching grant. Partial grants are not combined. These rights permit neither
signature nor publication. A registry-looking local tag is still only a local
name; it does not grant permission to push. Existing v1 publication/signing
policies remain valid and do not authorize construction.

Base references keep the builder's existing forms, including
`python@sha256:…`, `python:3.14-slim@sha256:…` and registry names with ports. They
are not validated as push destinations, normalized to another registry spelling
or matched by prefix. Each input reference is compared exactly, without resolving
paths, opening files or treating nested/sibling paths as covered by a grant.

The policy authorizes references and parameters, **not their bytes**. The plugin
still prepares bounded private snapshots, validates bundles statically, checks
wheel hashes and installs dependencies without an index. `inputs_sha256` is only
known after preparation; it is a build result, not a pre-authorized target field.
Timeout/log limits remain explicit runtime controls validated by the existing
request contract, outside the target grant. Project inputs cannot select or
extend the policy.

After preparing [build.json and the inputs](oci-service-plugin.md#build-and-run):

```sh
apizr plugins run apizr-oci build --arguments build.json \
  --operator-policy operator.json --timeout-ms 360000
```

The CLI and managed Python API refuse before plugin/tool execution, input reads
or Docker/network access. The same owned argument snapshot reaches the builder.
A successful build retains `published:false`, verified image/platform/input
identities and a nonprivileged image user. Apizr generates the Dockerfile; it
never executes a Dockerfile or build script supplied by the analyzed project.
`apizr expose build` still generates bundles and does not use this image-build
rule. Existing governed-worker policies are unchanged.

The base image or its metadata may require registry access even with cached
layers. `--network=none` limits Dockerfile build steps, not all daemon traffic.
This grant authorizes an invocation's parameters; it is not a daemon sandbox or
a guarantee about configured registry mirrors, DNS or redirects. Killing the
client does not confirm cancellation of daemon work: caches or unreported images
may remain. Existing cancellation, cleanup and result-verification limits apply.

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
protection. It snapshots the arguments, validates the shared operation contract,
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

## Authorize signing separately

`attest` needs its own grant. Installation, activation or a `publish` grant cannot
authorize use of a signing key. The complete [operator.json](../examples/operator.json)
includes this third rule, with fictitious identities. Use the exact reviewed
`apizr-attest` identity and full locked dependency closure from your installation.

In addition to `plugin`, `operation: attest` and the exact `repository`, specify:

| Field | Operator expectation |
| --- | --- |
| `key_id` | Exact 32-character lowercase hexadecimal key identifier |
| `expected_signer` | Exact 64-character lowercase hexadecimal public signer identity |
| `key_file` | Exact absolute local file reference from `attest.json`; no private key contents |
| `tsa_url` | Explicit RFC 3161 authority URL from `attest.json` |
| `permissions` | All three: `registry.read`, `receipt.sign`, `timestamp.request` |

One matching rule must contain all three rights. Partial rules are not combined.
Signing grants do not accept `registry.publish`; publication grants do not accept
signing or timestamp permissions. Existing v1 publication-only documents remain
valid and do not authorize signing. Add a separate signing rule to authorize it.

Key paths are compared as exact absolute strings, without resolving symlinks,
reading files or treating `/private/./operator.key` as `/private/operator.key`.
The reference is not a cryptographic identity of the file's bytes. The native
plugin must still verify the key, actual signer, timestamp and final receipt.
Keep keys and operator-selected files protected from untrusted writers.

TSA comparison uses scheme, hostname, effective port and exact path. Scheme and
hostname are case-insensitive; omitted ports mean 80 for HTTP or 443 for HTTPS;
an empty path means `/`. Other paths, ports and authorities stay distinct, with
no wildcard or prefix matching. Path escapes are not decoded, and paths are not
resolved: `%74imestamp` and `timestamp` are different policy inputs. Credentials,
queries, fragments, backslashes, control characters, percent-encoded hostnames
and invalid ports are refused; the URL is limited to 2,048 characters.
Both existing HTTP and HTTPS transports remain supported; HTTPS retains TLS
verification. RFC 3161 trust still comes from independently pinned certificates.

This decision authorizes the **initial URL passed to the native tool**. It does
not resolve DNS, pin the server's network address or impose a network sandbox on
the native client's redirect behavior. Select an authority you trust and retain
the existing cryptographic trust checks; authorization does not replace them.

Prepare the operational files using the [delivery guide](attest-delivery-plugin.md).
With matching, separately reviewed signing and publication grants:

```sh
# Sign and timestamp a verified delivery.
apizr plugins run apizr-attest attest --arguments attest.json \
  --operator-policy operator.json --timeout-ms 360000
# Verify an existing receipt offline; no signing grant or private key is needed.
apizr plugins run apizr-attest verify --arguments verify.json \
  --timeout-ms 180000
# Publish that existing receipt using a distinct publication grant.
apizr plugins run apizr-attest publish --arguments publish.json \
  --operator-policy operator.json --timeout-ms 360000
```

Signing does not publish the proof. After signing, verification and publication
can run with the private key unavailable. Publication still requires its own
repository read/publish authorization. A delivery receipt remains evidence of
verified delivery, **not supervision of the build**.

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
| `authorized` | This operation matches a complete grant |
| `not_required` | This operation is outside this first authorization scope |
| `operator_policy_required` | No policy was supplied |
| `operator_policy_invalid` / `operator_policy_unavailable` / `operator_policy_too_large` | Policy refused before invocation |
| `operator_arguments_invalid` | Operation arguments do not satisfy the shared contract |
| `operator_identity_denied` | Installed build/closure or official entry point does not match |
| `operator_operation_denied` | No matching operation grant |
| `operator_repository_denied` | No matching exact repository |
| `operator_permissions_denied` | The grant lacks a required build, registry, signing or timestamp permission |
| `operator_build_denied` | Base, platform, interface, paths, Docker parameters or local tag does not match |
| `operator_key_denied` | Key ID, expected signer or key file reference does not match |
| `operator_tsa_denied` | Timestamp authority does not match |

## Understand the boundary

This is admission control for **managed Apizr invocations**, not a sandbox against
a malicious trusted plugin. Directly invoking a plugin, Docker/ORAS/Attest or the
low-level `extension_runtime.invoke_extension` outside the managed installation
path does not acquire operator authorization. Protect operator files and plugin
storage from untrusted writers; plugins still execute with the user's rights.

This control covers image `build`/`push`, proof `publish` and delivery signing `attest`.
Git access, analysis and the other operations retain their existing controls;
`not_required` does not claim they have completed operator authorization.
`verify`, plugin lifecycle/catalog operations and the analysis
MCP server keep their behavior. Publication through MCP is not added.
