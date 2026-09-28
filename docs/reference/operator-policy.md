<span id="authorize-an-oci-publication"></span>
<span id="authorize-image-builds-signing-and-publication"></span>

# Authorize Git acquisition, image builds, signing and publication

!!! warning "Explicit authorization required"
    Remote `--git` commands and `acquire_snapshot` also require an explicit Git grant.
    Managed `outerspace-apizr-oci build`, `outerspace-apizr-oci push`, `outerspace-apizr-attest publish` and `outerspace-apizr-attest attest` calls require
    `--operator-policy`. An installed, active plugin alone does not permit
    building, publication or signing.

Installation puts verified wheel bytes in an isolated environment. Activation
chooses one installed version. **Authorization** permits a particular installed
build to perform one operation on explicitly selected inputs or a remote repository. None implies the next.

For prerequisites and package availability, see [Install Apizr](../getting-started/install.md).

## Authorize repository analysis

Repository analysis requires **source.analyze** for filesystem-backed `scan`, `graph`,
`readiness`, `expose plan` and the analysis phase of `expose build rest|mcp`.
Their Python APIs use the same pure `decide_analysis(policy, target)` decision.
This is independent of `git.fetch`, image construction, signing and publication.
It does not select public functions or permit business execution. These commands require an explicit
`--operator-policy` or the typed Python `operator_policy` argument.

A complete [local policy](../examples/operator-analysis-local.json):

```json
{
  "schema": "apizr.operator-policy/v1",
  "grants": [
    {
      "adapter": "repository",
      "operation": "analyze",
      "target": {
        "kind": "local",
        "root": "/work/project"
      },
      "permissions": [
        "source.analyze"
      ]
    }
  ]
}
```

Replace `/work/project` with the **canonical absolute root** actually used.
The exact root is authorized, including descendants subject to scan limits,
source roots and exclusions. It does not grant `/work/project-other`, another
root, or an independently requested child root. All path components are opened
without following symbolic links. Use the physical path (for example
`/private/tmp/project` on macOS), not a symlink alias. The directory descriptor
anchors traversal; changing a pathname cannot redirect it. MCP also pins the
root's device/inode and refuses replacement. Local file edits affect later
analyses: use the repository digest guard to detect changes between MCP calls.

```sh
apizr scan /work/project --operator-policy /private/operator.json --catalog
apizr graph /work/project --operator-policy /private/operator.json --graph
apizr readiness /work/project --operator-policy /private/operator.json --report
```

Explicitly selected, bounded project/operator/readiness/exposure configuration
may be read to determine the target and parameters. Source enumeration and reading
start only after admission. No authority is discovered from a project, profile,
catalogue or environment variable. Refusals exit 2 with a fixed JSON decision on
stderr, no partial report on stdout.

For Git, add a separate analysis grant with target
`{"kind":"git","repository":"https://git.example/team/project.git",
"reference":"refs/heads/main","subdir":"src"}`. Matching uses the exact requested
repository/ref/subdirectory, never a random temporary path. Both grants are
checked before combined CLI acquisition. The Python acquisition API separately
requires `git.fetch`; pass its **live GitSnapshot object**, plus analysis policy,
to the compiler. That object is bound to the actual acquisition, resolved commit
and opened export. Invented, copied or expired snapshots are refused. A branch
grant admits its name; the resolved commit identifies what was analyzed.
`subdir` does not bound all objects transferred during acquisition.

MCP captures the policy and project scope once at launch, preserving them across
exec and workers. Policy edits require a **restart**; there is no dynamic
revocation. Clients cannot choose roots or new authority. See the
[complete MCP example](apizr-mcp-server.md#choose-one-local-project).

## Authorize a Git source

Git is part of the minimal core, not an installed plugin. Use a separate
`adapter: git`, `operation: fetch` grant with `git.fetch` permission. Complete
[fictitious HTTPS](../examples/operator-git-https.json) and
[fictitious SSH](../examples/operator-git-ssh.json) policies show every field;
replace the example address, revision, subdirectory and absolute trust references
with values you have reviewed. Never obtain this policy from the source project.

The `target` binds `transport`, `repository`, `reference`, `subdir`, `ca_file`,
`ssh_agent_socket` and `ssh_known_hosts`. Repository strings, revision names and
subdirectories match **literally**: no URL decoding, hostname case folding,
default-port substitution, `.git` stripping, wildcard or prefix matching. An SCP
relative path is not an SSH absolute path; users and ports remain distinct.
Existing Git validators still reject unsafe URLs and ambiguous branch/tag names.

Trust references in a policy are absolute paths. API/CLI relative input paths
are made absolute against the caller's working directory before the decision,
without resolving symlinks, reading contents or collapsing `..` components.
The captured values are then used for acquisition. Existing SSH/CA technical
checks still run after authorization. Matching a path does **not** pin its bytes,
the agent's identities or a server certificate.

A branch grant authorizes that requested name, not a commit known in advance.
Git resolves it once, then analyzes and generates from that exact commit.
`subdir` selects the later analysis root: acquisition processes the repository
before selecting it. It is **not a confidentiality boundary** limiting which
objects are transferred or temporarily exported.

`acquire_snapshot(..., operator_policy=load_operator_policy(Path("operator.json")))`
applies the same gate as all four remote CLI commands. `decide_git(policy, target)`
uses a typed `GitTarget` and performs no I/O. Missing/invalid/insufficient policy
refuses before Git, SSH/helpers, network/agent access, trust-file reads or workspace
creation. The CLI emits the existing structured decision on stderr and exits 2;
the API raises `AuthorizationDenied`. Malformed source parameters retain their
fixed `GitSourceError` diagnostics. No plugin installation identity is fabricated.

Only the explicitly supplied policy grants authority. Neither `apizr.toml`,
remote files, a catalog/profile nor environment variables can select or extend it.
Local analysis commands require their own `source.analyze` grant; a fetch
grant does not authorize reading a local root. Acquisition limits remain separate
validated controls. The grant replaces neither server access rights nor TLS/SSH
trust and provides no build, signing or publication permission. Existing plugin
grants remain valid and do not authorize Git. See the complete
[HTTPS CLI/Python journey](git-sources.md) and [SSH journey](git-ssh.md).

Analysis authorization is a separate `source.analyze` rule; see the complete examples above.

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
for name, operation in (("outerspace-apizr-oci", "push"), ("outerspace-apizr-attest", "publish")):
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
| `operation` | `push` for outerspace-apizr-oci or `publish` for outerspace-apizr-attest |
| `repository` | Exact registry, optional explicit port, namespace and image repository; no tag, digest or wildcard |
| `permissions` | Both `registry.read` and `registry.publish` for this operation |

A rebuilt wheel with the same name/version, or a changed lock/dependency set,
needs a new grant. Reordering dependencies does not change identity. A grant must
contain both required permissions; separate partial grants are not combined.
No grant contains credentials, private key bytes or a free-form command.
Signing grants add explicit references as described below.

## Authorize an image build

Managed `outerspace-apizr-oci build` requires its own `operation: build` grant. The complete
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
apizr plugins run outerspace-apizr-oci build --arguments build.json \
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
apizr plugins run outerspace-apizr-oci push --arguments push.json \
  --operator-policy operator.json --timeout-ms 360000
apizr plugins run outerspace-apizr-attest publish --arguments publish.json \
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
`outerspace-apizr-attest` identity and full locked dependency closure from your installation.

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
apizr plugins run outerspace-apizr-attest attest --arguments attest.json \
  --operator-policy operator.json --timeout-ms 360000
# Verify an existing receipt offline; no signing grant or private key is needed.
apizr plugins run outerspace-apizr-attest verify --arguments verify.json \
  --timeout-ms 180000
# Publish that existing receipt using a distinct publication grant.
apizr plugins run outerspace-apizr-attest publish --arguments publish.json \
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
        "outerspace-apizr-oci",
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
| `operator_git_source_denied` | Exact Git source, revision, selection or trust references do not match |
| `operator_analysis_denied` | Exact analysis root or Git source does not match |
| `operator_source_invalid` / `operator_source_unavailable` / `operator_source_changed` | Invalid context, inaccessible/link traversal, or changed pinned identity |
| `operator_build_denied` | Base, platform, interface, paths, Docker parameters or local tag does not match |
| `operator_key_denied` | Key ID, expected signer or key file reference does not match |
| `operator_tsa_denied` | Timestamp authority does not match |

## Understand the boundary

This is admission control for **managed Apizr invocations**, not a sandbox against
a malicious trusted plugin. Directly invoking a plugin, Docker/ORAS/Attest or the
low-level `extension_runtime.invoke_extension` outside the managed installation
path does not acquire operator authorization. Protect operator files and plugin
storage from untrusted writers; plugins still execute with the user's rights.

This control covers managed repository analysis, Git acquisition, image
`build`/`push`, proof `publish` and signing `attest`. Single-file/notebook inspection
and primitives such as `scan_sources`, `build_graph`, `assess_repository` and
`plan_exposure` process caller-supplied bytes/artifacts in memory; they cannot
infer the authority under which those bytes were obtained. `render_bundle` uses
retained bytes without rereading sources. This is not universal protection against
arbitrary Python executed with the user's rights. Verification and plugin lifecycle
operations retain their controls. Publication through MCP is not added.
