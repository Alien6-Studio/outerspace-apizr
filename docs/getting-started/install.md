# Install Apizr

This documentation covers Apizr **0.4**. Install the core, then follow the
[Quickstart](quickstart.md). Add a plugin profile only when your workflow needs it.

## Install the core

Use Python 3.11–3.14, a POSIX shell and pip. Start in a new working directory:

```sh
mkdir apizr-workspace
cd apizr-workspace
python3 -m venv core
. core/bin/activate
python -m pip install outerspace-apizr==0.4.0.1
apizr --version
```

**Observe:** `outerspace-apizr 0.4.0.1`. Continue with the [Quickstart](quickstart.md)
to generate and call your first MCP or REST service. No plugin or Docker is needed.

With uv or pipx already installed, `uv tool install outerspace-apizr==0.4.0.1` or
`pipx install outerspace-apizr==0.4.0.1` is an alternative to the virtual environment
above. Use the executable path reported by your tool.

## Add optional plugin profiles

The plugins are not yet published on PyPI. The coordinated `0.4.0.1`
replacement is being qualified; its public packages
and tag are not yet available. The commands below target that exact delivery.
The previously published core is `0.4.0`. See the
[publication status](../releases/0.4.0.md#publication-status) before installing.
Keep the working directory above. These profiles install plugins separately and
do not change the core environment.

<span id="install-the-published-release"></span>
<span id="evaluate-the-040-candidate"></span>

### Obtain the installation files

You need Python 3.11–3.14, a POSIX shell, tar, and an authenticated GitHub CLI (`gh`)
that can download Actions artifacts and verify attestations. Plugin installation
also requires an already installed **uv**. None of these tools is installed by
Apizr. Use a new workspace, and select the export matching your interpreter,
system and architecture from the [target download table](#supported-targets).
Windows and other targets are not qualified by this matrix.

After publication, resolve the immutable `v0.4.0.1` tag and its latest successful
master CI run. This example selects **Linux x86-64 / CPython 3.11**. Keep the
packages and target export from that same verified run; older 0.4.0 exports use
different plugin identities and must not be mixed with these instructions.

```sh
export EXPECTED_COMMIT=$(gh api repos/Alien6-Studio/outerspace-apizr/git/ref/tags/v0.4.0.1 --jq .object.sha)
export REVIEWED_RUN_ID=$(gh run list --repo Alien6-Studio/outerspace-apizr --workflow ci.yml --branch master --event push --commit "$EXPECTED_COMMIT" --limit 1 --json databaseId,conclusion --jq '.[0] | select(.conclusion == "success") | .databaseId')
test -n "$EXPECTED_COMMIT" && test -n "$REVIEWED_RUN_ID"
export TARGET_ARTIFACT=release-target-ubuntu-latest-3.11
export PYTHON=python3.11
gh run view "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr
gh run download "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name release-candidate --dir release/candidate
gh run download "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name "$TARGET_ARTIFACT" --dir release/target-download
gh run download "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name build-attestations --dir release/evidence
gh attestation verify release/evidence/ci-evidence.tar.gz --bundle release/evidence/build-provenance.sigstore.json --repo Alien6-Studio/outerspace-apizr --signer-workflow Alien6-Studio/outerspace-apizr/.github/workflows/ci.yml --source-digest "$EXPECTED_COMMIT" --source-ref refs/heads/master
```

**Observe:** the run is successful and the attestation accepts the exact commit,
workflow and evidence archive. A PR preview has no master attestation and cannot
substitute for this approval. For another supported target, change only the target
artifact and installed interpreter using the table; inspect its recorded architecture.
Actions resources expire after 90 days; the final release will retain the approved
resources under [unique public names](../contributing/publish-0.4.md#release-attachment-inventory).

Bind **both** the catalog/dependency export and the package inventory to the verified
evidence, then verify all eight package hashes. This is a consistency check after
identity verification, not an independent trust decision:

```sh
"$PYTHON" - <<'PY'
import hashlib
import json
import os
import tarfile
from pathlib import Path
candidate = Path("release/candidate")
export = Path("release/target-download/target-export.tar.gz")
with tarfile.open("release/evidence/ci-evidence.tar.gz") as evidence:
    def approved(name, path):
        source = evidence.extractfile("./coordinated/" + name)
        assert source is not None
        digest = hashlib.file_digest(source, "sha256").hexdigest()
        with path.open("rb") as local:
            assert hashlib.file_digest(local, "sha256").hexdigest() == digest
    approved("release-candidate/candidate.json", candidate / "candidate.json")
    approved(os.environ["TARGET_ARTIFACT"] + "/target-export.tar.gz", export)
manifest = json.loads((candidate / "candidate.json").read_text())
assert manifest["commit"] == os.environ["EXPECTED_COMMIT"]
for item in manifest["artifacts"]:
    path = candidate / item["file"]
    assert path.stat().st_size == item["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
print("Verified candidate and complete target export")
PY
mkdir release/target
tar -xzf release/target-download/target-export.tar.gz -C release/target
export CANDIDATE="$PWD/release/candidate"
export TARGET="$PWD/release/target"
export CORE_DIR="$PWD/core"
```

`target.json` records the actual Python patch version, system and architecture.
Its file inventory covers catalogs, locks, notices inside wheels and dependency
bytes. Do not substitute other wheels after verification.

<span id="install-the-candidate-with-pip"></span>

### Install the core offline

Skip this step if you already installed the core above. As an offline alternative,
these commands install the same core from verified files in a new environment.
The selected `PYTHON` must match the target export's Python minor version.

<!-- install:pip -->
```sh
"$PYTHON" -m venv "$CORE_DIR"
"$CORE_DIR/bin/python" -m pip install --no-index --find-links "$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-0.4.0.1-py3-none-any.whl"
"$CORE_DIR/bin/apizr" --version
```

Observe `outerspace-apizr 0.4.0.1`, then activate it with `. "$CORE_DIR/bin/activate"`
and follow the [Quickstart](quickstart.md).

### Alternatively, install as a tool

With uv already installed, use this **instead of** pip:

<!-- install:uv -->
```sh
uv tool install --python "$PYTHON" --offline --no-index --find-links "$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-0.4.0.1-py3-none-any.whl"
```

Or, with pipx already installed, use:

<!-- install:pipx -->
```sh
pipx install --python "$PYTHON" --pip-args="--no-index --find-links=$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-0.4.0.1-py3-none-any.whl"
```

Use the executable path reported by that tool, then check `apizr --version`.
Do not install plugins with `pipx inject` or manually edit a uv tool environment.
The profile example below uses the principal pip path (`$CORE_DIR/bin/apizr`);
for tool installations use that reported Apizr executable instead.

## Choose a plugin profile

The **core** is enough for supported static analysis and generation. Generated
REST/MCP servers have separate runtime requirements. The **`outerspace-apizr-mcp` plugin**
is an analysis server; the historical **`mcp` extra** supplies optional dependencies
for existing core workflows and does not install that plugin.

| Profile | Plugins | Additional prerequisites when used |
| --- | --- | --- |
| `mcp` | outerspace-apizr-mcp | An MCP client; Python SDK proof needs no AI account |
| `oci` | outerspace-apizr-oci | Docker Engine and Buildx for build/push |
| `delivery` | outerspace-apizr-oci and outerspace-apizr-attest | Docker/Buildx; Continuum Attest for receipts; ORAS for proof transport |

From the verified installation workspace, choose **one** profile and absent plan
and plugin-store directories. The commands below are offline and reuse exported
requirements. Choose `oci` or `delivery` instead of `mcp` for those paths:

```sh
export PROFILE=mcp
export PLAN="$PWD/$PROFILE-plan"
export PLUGINS_DIR="$PWD/plugins"
```

<!-- install:profile -->
```sh
"$CORE_DIR/bin/apizr" plugins catalog resolve --profile "$PROFILE" --catalog "$TARGET/catalog/catalogue.json" --wheelhouse "$TARGET/wheelhouse" --output-dir "$PLAN" --json
"$CORE_DIR/bin/apizr" plugins lock check --project "$PLAN/apizr.toml" --lock "$PLAN/apizr.plugins.lock.json" --wheelhouse "$TARGET/wheelhouse" --json
"$CORE_DIR/bin/apizr" plugins sync --project "$PLAN/apizr.toml" --lock "$PLAN/apizr.plugins.lock.json" --wheelhouse "$TARGET/wheelhouse" --plugins-dir "$PLUGINS_DIR" --json
"$CORE_DIR/bin/apizr" plugins list --active --json --plugins-dir "$PLUGINS_DIR"
```

**Observe:** resolution and lock checking succeed; sync records installations.
On this fresh store, the active inventory is empty. Activate only what you selected:

```sh
# mcp profile
"$CORE_DIR/bin/apizr" plugins enable outerspace-apizr-mcp --version 0.4.0.1 --plugins-dir "$PLUGINS_DIR"
# oci profile: enable outerspace-apizr-oci instead
# delivery profile: enable both outerspace-apizr-oci and outerspace-apizr-attest
```

**Installation** verifies and stores bytes. **Activation** selects an installed
version. **Authorization** permits a particular operation and target; neither
installation nor activation grants it. The [analysis MCP guide](../reference/apizr-mcp-server.md)
provides a complete project, operator grant and client configuration. The
[OCI](../reference/oci-service-plugin.md) and [Attest](../reference/attest-delivery-plugin.md)
guides explain explicit image publication and signing permissions. These are
trusted programs running with user rights, not a universal sandbox.

## Supported targets

Choose the artifact and interpreter for your machine. All exports below belong
to the same verified run selected above.
The exact patch version and architecture are recorded in `target.json`.

| System / architecture | Python | Target artifact |
| --- | --- | --- |
| Linux x86-64 | 3.11 | `release-target-ubuntu-latest-3.11` |
| Linux x86-64 | 3.12 | `release-target-ubuntu-latest-3.12` |
| Linux x86-64 | 3.13 | `release-target-ubuntu-latest-3.13` |
| Linux x86-64 | 3.14 | `release-target-ubuntu-latest-3.14` |
| macOS arm64 | 3.11 | `release-target-macos-latest-3.11` |
| macOS arm64 | 3.14 | `release-target-macos-latest-3.14` |

## Develop from source

Contributors should follow [development and checks](developer-guide/setup.md).
[Manual wheel preparation](../development/0.4.md#install-a-development-wheel)
and the guides' advanced sections remain available for custom evaluation builds.
Those builds have their own identities and cannot replace approved release bytes.
See [migration](migrate-0.4.md) before replacing development locks, grants or activations.
