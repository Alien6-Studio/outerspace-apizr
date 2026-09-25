# Build and publish REST and MCP service images

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../development/0.4.md#install-a-development-wheel) and record its source commit.

The official `apizr-oci` extension builds a **local service image** from a direct
repository exposure bundle and publishes it through a separate, explicit `push`
operation. It does not build governed execution workers or install business
dependencies. Install and enable it explicitly;
the minimal Apizr environment does not acquire Docker, REST or MCP dependencies.
This first package is version `0.0.0`, available from the checkout, not published.

## Prerequisites and installation

Use Python 3.11–3.14, uv, Docker Engine with BuildKit/Buildx, and an explicit local
Unix socket. The target is `linux/amd64` or `linux/arm64`. Cross-platform builds
require an already configured emulator; Apizr does not install one. Choose and
review a Python base image with `python`, `venv` and pip, pinned by SHA-256 digest.
The base, Docker binaries and dependency wheels remain trusted code.

Build the two wheels, then leave the checkout. These preparation commands may
access package indexes; installation through `apizr plugins install` is offline.
The plugin gets its own copy of Apizr's validation code and Pydantic in its own
locked environment. No Docker SDK is required anywhere.

```sh
work=$(mktemp -d)
uv build --wheel --out-dir "$work/plugin-wheels"
uv build --wheel plugins/oci --out-dir "$work/plugin-wheels"
cd "$work"
uv venv --seed --python 3.14 prepare
prepare/bin/python -m pip download --only-binary=:all: --dest plugin-wheels \
  plugin-wheels/outerspace_apizr-0.3.0-py3-none-any.whl \
  plugin-wheels/apizr_oci-0.0.0-py3-none-any.whl
uv venv --python 3.14 core
uv pip install --python core/bin/python --offline --no-index \
  --find-links plugin-wheels plugin-wheels/outerspace_apizr-0.3.0-py3-none-any.whl
```

Create `lock_wheels.py` for the reviewed wheels downloaded for **this** interpreter
and platform. It records the exact bytes; hashes establish integrity, not trust
in the author. Keep one wheel per distribution and all transitive dependencies.
Do not include sdists or unrelated wheels.

```python
import hashlib
import sys
import zipfile
from email.parser import BytesParser
from pathlib import Path

lines = []
for wheel in sorted(Path(sys.argv[1]).glob("*.whl")):
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        metadata = BytesParser().parsebytes(archive.read(name))
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    lines.append(f"{metadata['Name']}=={metadata['Version']} --hash=sha256:{digest}\n")
Path(sys.argv[2]).write_text("".join(lines))
```

```sh
prepare/bin/python lock_wheels.py plugin-wheels plugin.lock
plugin_sha=$(prepare/bin/python -c 'import hashlib; from pathlib import Path; print(hashlib.sha256(Path("plugin-wheels/apizr_oci-0.0.0-py3-none-any.whl").read_bytes()).hexdigest())')
core/bin/apizr plugins install plugin-wheels/apizr_oci-0.0.0-py3-none-any.whl \
  --sha256 "$plugin_sha" --requirements plugin.lock --wheelhouse plugin-wheels \
  --plugins-dir "$work/plugins"
core/bin/apizr plugins enable apizr-oci --version 0.0.0 --plugins-dir "$work/plugins"
```

The lock uses the existing restricted requirements syntax: `name==version
--hash=sha256:HEX`, one SHA-256 per package, comments and continuations allowed.
Includes, URLs, paths, index options, markers, extras and editable installs are
refused. Wheel archive and startup-file protections are reused. Metadata identity
and dependency headers retain their 64 KiB bound; unused long descriptions are
not parsed or loaded. Compressed/expanded archive limits still apply.

## Generate a bundle and prepare server dependencies

Use the existing Git workflow, with a reviewed commit and local policies:

```sh
core/bin/apizr expose build rest --git "$REPOSITORY_HTTPS_URL" --ref "$COMMIT" \
  --policy exposure.json --readiness-policy readiness.json --output-dir rest-bundle
core/bin/apizr expose build mcp --git "$REPOSITORY_HTTPS_URL" --ref "$COMMIT" \
  --policy exposure.json --readiness-policy readiness.json --output-dir mcp-bundle
```

Both policies must explicitly allow `direct` execution. The exposure policy
selects the capabilities and includes `rest` and `mcp` as appropriate. See
[Git sources](git-sources.md) for a complete acquisition example.

For each interface, resolve and download the server wheels using the **target**
Python image/platform, then create the lock. This preparation may access an
index; the subsequent build installs only the checked local wheel snapshot.
Example for REST, replacing the digest with the base you reviewed:

```sh
base=python@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2
platform=linux/amd64
mkdir rest-wheels
docker pull --platform "$platform" "$base"
docker run --rm --user "$(id -u):$(id -g)" --env HOME=/tmp --platform "$platform" \
  --mount "type=bind,src=$work/rest-wheels,dst=/wheels" \
  --mount "type=bind,src=$work/rest-bundle/requirements.txt,dst=/requirements.txt,readonly" \
  "$base" python -m pip download --only-binary=:all: --dest /wheels -r /requirements.txt
prepare/bin/python lock_wheels.py rest-wheels rest.lock
```

Use `mcp-bundle/requirements.txt`, `mcp-wheels` and `mcp.lock` for MCP. Do not use
macOS wheels in a Linux image. pip performs the resolution and compatibility
checks. The resolved server dependency closure must equal the lock; additional
business packages are refused. Installations require hashes, no index, no source
builds and no network in Dockerfile `RUN` instructions. Base-image resolution may
still contact its registry even when layers are cached; `--network=none` does
not prevent that. The build operation does not accept registry credentials or private base images.

## Build and run

A complete `build.json` (replace the absolute paths with your prepared paths):

```json
{
  "schema": "apizr.oci-build/v1",
  "bundle": "/tmp/apizr-example/rest-bundle",
  "interface": "rest",
  "base_image": "python@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2",
  "platform": "linux/amd64",
  "tag": "apizr-service:rest-example",
  "requirements": "/tmp/apizr-example/rest.lock",
  "wheelhouse": "/tmp/apizr-example/rest-wheels",
  "docker": {
    "executable": "/usr/bin/docker",
    "socket": "/var/run/docker.sock",
    "buildx": null
  },
  "timeout_ms": 300000,
  "max_log_bytes": 1048576
}
```

`buildx: null` uses Docker's system-installed Buildx. When it is not installed
system-wide, pass its absolute executable path, for example
`/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx` with Docker
Desktop. Its user socket is usually `$HOME/.docker/run/docker.sock`. The build
uses a fresh Docker configuration; it does not load user contexts, credential
helpers, authentication headers or inherited `DOCKER_*` variables. Only the
explicit binary, Buildx and socket are used. TCP/SSH Docker endpoints are not
supported in this pass.

```sh
core/bin/apizr plugins run apizr-oci build --arguments build.json \
  --timeout-ms 360000 --plugins-dir "$work/plugins"
docker run --rm --publish 127.0.0.1:8000:8000 apizr-service:rest-example
curl --fail -H 'Content-Type: application/json' \
  -d '{"a":2,"b":3}' http://127.0.0.1:8000/capabilities/calculator.add
```

For MCP, set `interface` to `mcp`, use its bundle/lock/wheelhouse and a different
tag, then build the same way. Start it with `docker run --rm --interactive TAG`
(no TTY): it speaks MCP stdio. The plugin and Docker build logs never share the
service's protocol stdout. REST binds `0.0.0.0:8000`; both images run as numeric
user `65532:65532` without a mounted Docker socket. Business code is loaded only
when the generated service starts, with its existing bundle integrity checks.

The outer `apizr.extension/v1` response contains `result.tag`, `platform`,
`image_id`, `inputs_sha256` and `published: false`. BuildKit's metadata and Docker
inspection must agree before success. `image_id` is the **local Engine identity**
(classic and containerd stores differ); it is not a claim about a manifest
published in a registry. `inputs_sha256` hashes the canonical path/hash map of
private build inputs, including wheels, bundle, lock, generated Dockerfile and
target. It does not promise bit-reproducible Docker layers or attest provenance.

## Limits and cancellation

Only direct repository bundles are accepted. The plugin calls `validate_bundle`,
never `load_bundle`, during preparation. It copies only canonical declared files,
not an entire directory, and ignores unrelated Dockerfiles, `.git`, `.env` and SSH
files. Declared symlinks, path traversal and special files are refused. A bundle
is limited to 4,096 declared files / 64 MiB total, its manifest to 1 MiB. The
existing lock limits apply: 64 KiB lock, 128 wheels, 64 MiB per wheel, 256 MiB total
compressed and 512 MiB total expanded. Prepared private bytes, not mutable source
paths, reach Docker.

Plugin build duration defaults to 300,000 ms and is limited to 540,000 ms. Client
stdout/stderr share a 1 MiB default budget (configurable to at most 16 MiB) and
are counted while read. `plugins run --timeout-ms` accepts 1–600,000 ms and keeps
its existing 10,000 ms default; allow headroom for startup, preparation and cleanup.
The plugin's temporary context lives under the extension runtime's owned working
directory, so runtime interruption removes it even when the plugin is killed.
The Python `build(..., workspace=...)` API requires caller-owned scratch storage;
use the existing extension runtime for process-group ownership and cancellation.

**Killing the Docker client does not prove that daemon work stopped.** A timed-out
or interrupted call returns no successful image result. A daemon build, cache or
unreported image may remain, including a tag assigned just before interruption.
No global prune or deletion of previous user images occurs. Use disposable Docker
runners for build tests and inspect the explicitly chosen tag before retrying.
This mechanism is not a sandbox or a daemon resource quota.

The [proof script](https://github.com/Alien6-Studio/outerspace-apizr/blob/master/scripts/smoke_oci_plugin.py)
installs both packages outside the checkout, acquires a real HTTPS Git fixture,
builds and calls REST/MCP after removing sources and bundles, interrupts after an
explicit Docker progress handshake, and compares all core files/distributions.
The dedicated CI runner preserves its results, locks and build inputs. In this
script's default build-only mode, no image is published; only named test
containers/images are removed. The separate publication proof is described below.

References: [Docker build metadata and network semantics](https://docs.docker.com/reference/cli/docker/buildx/build/),
[pip hash-checked installs](https://pip.pypa.io/en/stable/topics/secure-installs/).

## Publish a verified service image

The same installed plugin accepts `push`. It never rebuilds the image, imports
its sources or installs dependencies. Keep the complete `build` result, including
`image_id`, `platform` and `inputs_sha256`; `build` still returns `published:false`.

Prepare a dedicated Docker authentication file outside the project, readable only
by your user. This first version accepts exactly one `auths` entry, keyed by the
exact registry hostname and optional port. Its only field is `auth`: the base64
encoding of `username:password-or-token`. Base64 is not encryption. Credential
helpers, identity-token records, other registries and other Docker configuration
keys are refused. For `docker.io` (or its `index.docker.io` alias), the selected
record is copied under Docker's historical `https://index.docker.io/v1/` key in
the private configuration. Apizr never performs `docker login` or modifies your
Docker configuration. Do not commit this file or print its contents.

With the identity values from your build, a complete `/work/push.json` is:

```json
{
  "schema": "apizr.oci-push/v1",
  "image_id": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "platform": "linux/amd64",
  "inputs_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "destination": "registry.example.com:5443/services/calculator:0.4-test",
  "docker": {
    "executable": "/usr/bin/docker",
    "socket": "/var/run/docker.sock",
    "buildx": "/usr/libexec/docker/cli-plugins/docker-buildx"
  },
  "authentication": {
    "config_file": "/work/credentials/registry-auth.json",
    "ca_file": "/work/credentials/registry-ca.pem"
  },
  "timeout_ms": 300000,
  "max_log_bytes": 1048576
}
```

Replace the example digests and absolute paths with your actual build result and
Docker installation. `ca_file` is optional for a registry using a publicly trusted
certificate. A supplied PEM file adds explicit trust for Docker's registry clients;
it never disables certificate or hostname validation. The explicitly selected
Docker daemon must independently trust the registry CA. Configure that trust before
invocation; the plugin does not modify the daemon. Daemons with explicitly insecure
registries or non-default insecure CIDRs are refused. The daemon and its network
configuration remain trusted prerequisites; do not resolve registry names to the
daemon's implicitly insecure loopback network.

```bash
apizr plugins run apizr-oci push --arguments /work/push.json --timeout-ms 360000
```

The Python API is `apizr_oci.push(PushRequest.model_validate(document),
workspace=owned_directory, cancel=event)`, inside the installed plugin environment.
Use the existing extension runtime to supervise it from the core.

Publication requires Docker Engine API 1.46+ and Buildx. Destination references
must include a DNS registry name (optionally a port), a namespace, an image and an
explicit tag. IP literals, URL schemes, credentials in references and implicit
`latest` are not accepted. There is no authentication fallback.

### Identity and publication states

The local image is inspected by its immutable ID; its platform, non-root user and
Apizr input label must match. Docker's upload command requires a tag, so the plugin
creates a fresh `apizr-upload-<random>` staging alias from that ID, uploads it, and
verifies its remote identity before promoting its **digest** with Buildx. Moving
the original build tag cannot change the selected image. Staging tags can remain
locally and remotely, including after interruption. No remote deletion is attempted.

An existing destination is accepted only when it identifies the expected image.
A different image is refused. Only Docker's exact manifest-not-found diagnostic is
accepted as absence; authorization, certificate, network and other errors fail
closed. The tag is checked again immediately before promotion. These checks are
**not a registry lock**: another writer can race them or later change the tag.
Use registry-enforced immutable tags or exclusive write permissions when needed.

The versioned `apizr.oci-push-result/v1` result includes:

- `destination`: the requested tag;
- `digest_reference`: `registry/namespace/image@sha256:...`, usable for pulling;
- `image_id`: the requested immutable local ID;
- `config_digest`: the remote image configuration digest;
- `manifest_digest`: the verified single-platform manifest digest;
- `index_digest`: `null` (indexes and multiarchitecture publication are refused);
- `platform`, `inputs_sha256` and `published:true`.

Classic Docker uses a configuration digest as the local ID; containerd-backed
Docker can use a manifest digest. These identities are checked separately.
The plugin validates Docker's structured manifest response and its raw-byte
SHA-256, then verifies both the destination and digest-pinned retrieval reference.
It reports `published:true` only after all checks succeed.

Any failure after upload starts produces `remote_state_unconfirmed` in the plugin
protocol/Python API. The core CLI deliberately redacts plugin failures to
`plugin_failed`; **a CLI failure is not evidence that nothing was published**.
Cancellation also cannot prove that the daemon stopped or that the registry rolled
back a transfer. Inspect the registry before deciding what to do next. No rollback
or deletion is promised, and no logs or credentials are returned as diagnostics.

### Disposable integration proof

```bash
uv run --locked python scripts/smoke_oci_registry.py --output /tmp/apizr-registry-proof
```

This requires Docker with privileged disposable containers. It creates an isolated
network, a fresh authenticated HTTPS registry, a dedicated certificate, and two
independent Docker daemons. It installs the core and plugin wheels outside the
checkout, builds and publishes REST/MCP services, pulls by digest into the second
daemon, removes the sources and bundles, and calls both services. It compares the
core files and distributions before and after. Only the fixture's own resources
are removed. Certificate keys and credentials stay in its disposable volume and
are excluded from retained proof artifacts. Image/base/package downloads occur
only as explicit fixture preparation; test pushes target only this local registry.

Docker semantics used here are documented in
[image push](https://docs.docker.com/reference/cli/docker/image/push/),
[manifest inspect](https://docs.docker.com/reference/cli/docker/manifest/inspect/)
and [Buildx imagetools create](https://docs.docker.com/reference/cli/docker/buildx/imagetools/create/).
