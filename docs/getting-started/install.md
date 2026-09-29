# Install Apizr

These instructions cover the published stable **Apizr 0.4.1** release. Its
[publication status](../releases/0.4.1.md#publication-status) records the verified
source, archives and public delivery.

Install the core, then follow the
[Quickstart](quickstart.md). Add a plugin profile only when your workflow needs it.

## Install the core

Use Python 3.11–3.14, a POSIX shell and pip. Start in a new working directory:

```sh
mkdir apizr-workspace
cd apizr-workspace
python3 -m venv core
. core/bin/activate
python -m pip install outerspace-apizr==0.4.1
apizr --version
```

**Observe:** `outerspace-apizr 0.4.1`. Continue with the [Quickstart](quickstart.md)
to generate and call your first MCP or REST service. No plugin or Docker is needed.

With uv or pipx already installed, `uv tool install outerspace-apizr==0.4.1` or
`pipx install outerspace-apizr==0.4.1` is an alternative to the virtual environment
above. Use the executable path reported by your tool.

## Add optional plugin profiles

The coordinated packages are `outerspace-apizr==0.4.1`,
`outerspace-apizr-oci==0.4.1`, `outerspace-apizr-mcp==0.4.1` and
`outerspace-apizr-attest==0.4.1`. The
[release record](../releases/0.4.1.md#publication-status) identifies the qualified
final archives. These profiles install plugins separately and preserve the core.

<span id="install-the-published-release"></span>
<span id="evaluate-the-040-candidate"></span>

### Obtain the installation files

Use the **durable GitHub release assets**, not expiring Actions artifacts, for
normal installation. The commands below use the published **v0.4.1** assets.
You need Python 3.11–3.14, a POSIX shell, tar, GitHub CLI (`gh`) for public resource
retrieval/provenance verification, and an already installed **uv** for plugins.
Select your system, architecture and Python from [Supported targets](#supported-targets).

This selection uses Linux x86-64 / Python 3.11. The published inventory supplies
the exact patch-level export and source commit. Keep all files from the same release:

```sh
export APIZR_VERSION=0.4.1
export RELEASE_TAG=v0.4.1
export PYTHON=python3.11
export TARGET_PATTERN="apizr-${APIZR_VERSION}-linux-x86_64-cpython-3.11.*.tar.gz"
mkdir -p release/assets release/candidate/dist release/target-download
export EXPECTED_COMMIT=$(gh api "repos/Alien6-Studio/outerspace-apizr/commits/$RELEASE_TAG" --jq .sha)
gh release download "$RELEASE_TAG" --repo Alien6-Studio/outerspace-apizr --dir release/assets \
  --pattern candidate.json --pattern release-assets.json --pattern SHA256SUMS \
  --pattern 'outerspace_apizr*' --pattern "$TARGET_PATTERN" \
  --pattern ci-evidence.tar.gz --pattern build-provenance.sigstore.json
gh attestation verify release/assets/ci-evidence.tar.gz \
  --bundle release/assets/build-provenance.sigstore.json \
  --repo Alien6-Studio/outerspace-apizr \
  --signer-workflow Alien6-Studio/outerspace-apizr/.github/workflows/ci.yml \
  --source-digest "$EXPECTED_COMMIT" --source-ref refs/heads/release/0.4.1
```

Bind the selected export and candidate inventory to the attested CI evidence,
then verify the eight package hashes and the downloaded checksum entries. Local
copies below preserve the exact bytes and provide the layout used by the offline
commands; they do not reconstruct any package:

```sh
"$PYTHON" - <<'PYTHON'
import fnmatch
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path
assets = Path("release/assets")
candidate = Path("release/candidate")
inventory = json.loads((assets / "release-assets.json").read_text())
assert inventory["version"] == os.environ["APIZR_VERSION"]
assert inventory["commit"] == os.environ["EXPECTED_COMMIT"]
assert inventory["source_ref"] == "refs/heads/release/0.4.1"
checksums = dict(line.split("  ", 1)[::-1] for line in (assets / "SHA256SUMS").read_text().splitlines())
for path in assets.iterdir():
    if path.name != "SHA256SUMS":
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == checksums[path.name]
exports = [item for item in inventory["artifacts"] if fnmatch.fnmatch(item["file"], os.environ["TARGET_PATTERN"])]
assert len(exports) == 1, "Select exactly one qualified target export"
export = exports[0]
assert export["evidence_member"].startswith("coordinated/release-target-")
assert export["evidence_member"].endswith("/target-export.tar.gz")
with tarfile.open(assets / "ci-evidence.tar.gz") as evidence:
    def approved(member, path):
        source = evidence.extractfile("./" + member)
        assert source is not None
        with path.open("rb") as local:
            assert hashlib.file_digest(local, "sha256").hexdigest() == hashlib.file_digest(source, "sha256").hexdigest()
    approved("coordinated/release-candidate/candidate.json", assets / "candidate.json")
    approved(export["evidence_member"], assets / export["file"])
manifest = json.loads((assets / "candidate.json").read_text())
assert manifest["commit"] == os.environ["EXPECTED_COMMIT"]
assert manifest["version"] == os.environ["APIZR_VERSION"]
assert len(manifest["artifacts"]) == 8
for item in manifest["artifacts"]:
    name = Path(item["file"]).name
    path = assets / name
    assert path.stat().st_size == item["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
    shutil.copyfile(path, candidate / "dist" / name)
shutil.copyfile(assets / "candidate.json", candidate / "candidate.json")
shutil.copyfile(assets / export["file"], "release/target-download/target-export.tar.gz")
print("Verified release candidate and complete target export")
PYTHON
mkdir release/target
tar -xzf release/target-download/target-export.tar.gz -C release/target
export CANDIDATE="$PWD/release/candidate"
export TARGET="$PWD/release/target"
export CORE_DIR="$PWD/core"
```

Inspect the qualification report and `target.json` before installation: your
interpreter must match the recorded target. Release engineers can still use
[Actions artifacts for exact qualification](../contributing/releases.md); PR
previews cannot substitute for the final release's attested resources.

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
"$CORE_DIR/bin/python" -m pip install --no-index --find-links "$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-${APIZR_VERSION:-0.4.1}-py3-none-any.whl"
"$CORE_DIR/bin/apizr" --version
```

Observe `outerspace-apizr 0.4.1`, then activate it with `. "$CORE_DIR/bin/activate"`
and follow the [Quickstart](quickstart.md).

### Alternatively, install as a tool

With uv already installed, use this **instead of** pip:

<!-- install:uv -->
```sh
uv tool install --python "$PYTHON" --offline --no-index --find-links "$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-${APIZR_VERSION:-0.4.1}-py3-none-any.whl"
```

Or, with pipx already installed, use:

<!-- install:pipx -->
```sh
pipx install --python "$PYTHON" --pip-args="--no-index --find-links=$TARGET/base" "$CANDIDATE/dist/outerspace_apizr-${APIZR_VERSION:-0.4.1}-py3-none-any.whl"
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
"$CORE_DIR/bin/apizr" plugins enable outerspace-apizr-mcp --version "${APIZR_VERSION:-0.4.1}" --plugins-dir "$PLUGINS_DIR"
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

Choose the release export pattern and interpreter for your machine. Final exports
will be listed in the final release inventory after qualification/publication;
patterns below do not claim that final assets already exist. Each export records
its exact patch version and architecture.

| System / architecture | Python | Release export pattern |
| --- | --- | --- |
| Linux x86-64 | 3.11 | `apizr-0.4.1-linux-x86_64-cpython-3.11.*.tar.gz` |
| Linux x86-64 | 3.12 | `apizr-0.4.1-linux-x86_64-cpython-3.12.*.tar.gz` |
| Linux x86-64 | 3.13 | `apizr-0.4.1-linux-x86_64-cpython-3.13.*.tar.gz` |
| Linux x86-64 | 3.14 | `apizr-0.4.1-linux-x86_64-cpython-3.14.*.tar.gz` |
| macOS arm64 | 3.11 | `apizr-0.4.1-macos-arm64-cpython-3.11.*.tar.gz` |
| macOS arm64 | 3.14 | `apizr-0.4.1-macos-arm64-cpython-3.14.*.tar.gz` |

## Develop from source

Contributors should follow [development and checks](developer-guide/setup.md).
[Manual wheel preparation](../development/0.4.md#install-a-development-wheel)
and the guides' advanced sections remain available for custom evaluation builds.
Those builds have their own identities and cannot replace approved release bytes.
Review [plugin locks](../reference/project-plugin-locks.md) and
[operator permissions](../reference/operator-policy.md) before replacing
development locks, grants or activations.
