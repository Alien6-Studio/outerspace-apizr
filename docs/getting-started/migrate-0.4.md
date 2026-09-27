# Migrate from 0.3 to 0.4

**0.4.0 is being prepared; the published stable release remains 0.3.0.**
This guide applies to the development compiler and the upcoming 0.4.0 release.
Keep the [stable Quickstart](quickstart.md) for the published 0.3.0 package.
See the [0.4.0 notes](../releases/0.4.0.md) for the complete scope and limits.

## Prepare a separate installation

Keep your existing environment and generated bundles while validating the change.
Use the retained artifacts from a reviewed successful CI run; there is no need to
build the plugins or manually resolve their dependencies. The following example
is for **Linux x86-64 / CPython 3.11** with `gh`, Python 3.11 and uv already installed.
It downloads a candidate, not a published release. Set `REVIEWED_RUN_ID` to the
reviewed run and retain its commit from `gh run view`.

```sh
gh run view "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr
gh run download "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name release-candidate --dir release/candidate
gh run download "$REVIEWED_RUN_ID" --repo Alien6-Studio/outerspace-apizr --name release-target-ubuntu-latest-3.11 --dir release/target-download
mkdir release/target
tar -xzf release/target-download/target-export.tar.gz -C release/target
python3.11 -m venv core
core/bin/python -m pip install --no-index --find-links release/target/base release/candidate/dist/outerspace_apizr-0.4.0-py3-none-any.whl
```

`candidate.json` identifies the source commit and the eight distribution filenames,
sizes and SHA-256 values. `target.json` identifies the dependency target and every
exported file; `qualification.json` records actual checks and measurements.
Verify these records against the selected run and its checksums before installation.
For published release bytes, follow the [provenance verification procedure](../contributing/verification.md).

Other exported targets are Linux CPython 3.12/3.13/3.14 and macOS CPython 3.11/3.14;
select the corresponding `release-target-<runner>-<python>` artifact and inspect
its actual system/architecture before use. They are **target-specific**, not
universal wheelhouses. Windows and other Python/platform combinations are not
qualified by this matrix.

For an isolated CLI tool instead, the same base wheels work with:

```sh
uv tool install --python python3.11 --offline --no-index --find-links release/target/base release/candidate/dist/outerspace_apizr-0.4.0-py3-none-any.whl
pipx install --python python3.11 --pip-args="--no-index --find-links=release/target/base" release/candidate/dist/outerspace_apizr-0.4.0-py3-none-any.whl
```

Choose one installation method; do not run all three into your normal tool paths.
Qualification uses separate disposable tool homes. `pipx` itself is an explicit
prerequisite for its command. Plugins never require `pipx inject` or editing a uv
tool environment. Historical extras use the `extras` wheelhouse with the same core
wheel, for example `...whl[legacy]`; they are separate from plugin dependencies.

To develop Apizr rather than consume an exported candidate, the
[development installation](../development/0.4.md#install-a-development-wheel)
remains available. That builds new evaluation artifacts and does not substitute
for the retained candidate's qualification.

For the local example below, activate the separate `core` environment in your
working directory:

```sh
. core/bin/activate
apizr --version
```

The coordinated candidate wheel reports `0.4.0`; the candidate commit and archive
hashes identify the candidate being qualified, not an already published package. Do not substitute a nonexistent
`outerspace-apizr==0.4.0` index installation. Official versions and artifact hashes
will be supplied by the verified release record.

## Authorize a local repository

The following example is self-contained. Start in your working directory with the
new environment activated. Use an absent `migration-demo` directory; the example
keeps generated files outside the source directory.

First create two ordinary Python functions and the policies. **Readiness** assesses
the code evidence, **exposure** selects public functions, and **operator authority**
permits reading this exact source root. They are separate inputs.

<!-- migration:prepare -->
```sh
mkdir migration-demo
cd migration-demo
mkdir repository
cat > repository/api.py <<'PY'
def quote(unit_price: float, quantity: int = 1) -> float:
    return unit_price * quantity
PY
cat > repository/inventory.py <<'PY'
def available(stock: int, requested: int = 1) -> bool:
    return stock >= requested
PY
cat > readiness.json <<'JSON'
{"execution":{"modes":["direct"]}}
JSON
cat > exposure.json <<'JSON'
{"selection":{"include":["python:api:quote","python:inventory:available"]},"interfaces":["rest","mcp"],"execution":{"allowed":["direct"]}}
JSON
python - <<'PY'
import json
from pathlib import Path
root = str(Path("repository").resolve())
Path("operator.json").write_text(json.dumps({
    "schema": "apizr.operator-policy/v1",
    "grants": [{
        "adapter": "repository", "operation": "analyze",
        "target": {"kind": "local", "root": root},
        "permissions": ["source.analyze"]
    }]
}))
PY
```
<!-- /migration:prepare -->

`operator.json` authorizes only that canonical absolute repository root.
It does not authorize a neighboring directory, follow symlinks or make functions
public. For your own code, explicitly choose the root and selected capability IDs;
do not accept an operator policy supplied by the project or a remote client.

An old repository command without the grant now fails before source reads:

<!-- migration:refuse -->
```sh
apizr expose plan repository --readiness-policy readiness.json --policy exposure.json --plan
```
<!-- /migration:refuse -->

Expect exit **2**, a structured `operator_policy_required` refusal on stderr and
no plan on stdout. Add the explicit policy to plan and generate:

<!-- migration:generate -->
```sh
apizr expose plan repository --operator-policy operator.json --readiness-policy readiness.json --policy exposure.json --plan > plan.json
apizr expose build rest repository --operator-policy operator.json --readiness-policy readiness.json --policy exposure.json --output-dir build/rest
apizr expose build mcp repository --operator-policy operator.json --readiness-policy readiness.json --policy exposure.json --output-dir build/mcp
```
<!-- /migration:generate -->

Expect a plan selecting `python:api:quote` and `python:inventory:available`, a REST
bundle with `openapi.json`, and an MCP bundle with `mcp-tools.json` and `server.py`.
Output directories must be absent or empty. Generation already performs the
necessary analysis and planning; separate `scan`, `graph` and `readiness` commands
are optional diagnostics, not prerequisites. They accept the same
`--operator-policy operator.json` option.

These commands generate files without running the project. To serve and call
them, install each bundle's `requirements.txt` in its own environment and follow
the [REST/MCP bundle instructions](user-guide/exposure.md#build-a-direct-repository-bundle). The expected
function results are `quote(12.5, 2) = 25.0` and `available(10, 3) = true`.
Execution requires trusted source and dependencies; an analysis grant is not
an execution safety guarantee.

## Pass the same authority from Python

There is no CLI subprocess or implicit policy-file lookup. Load the policy once
and pass it to the shared compiler. From `migration-demo`, the following produces
the same plan and bundle bytes as the preceding CLI commands:

<!-- migration:python -->
```sh
python - <<'PY'
from pathlib import Path
from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy, plan_bytes
from apizr.operator_policy import load_operator_policy
from apizr.repository_readiness import RepositoryReadinessPolicy

prepared = prepare_exposure(
    Path("repository"),
    operator_policy=load_operator_policy(Path("operator.json")),
    readiness_policy=RepositoryReadinessPolicy.model_validate_json(
        Path("readiness.json").read_bytes()
    ),
    policy=ExposurePolicy.model_validate_json(Path("exposure.json").read_bytes()),
)
assert plan_bytes(prepared.plan) == Path("plan.json").read_bytes()
for interface in ("rest", "mcp"):
    bundle = render_bundle(prepared, interface=interface)
    assert all(
        (Path("build") / interface / name).read_bytes() == data
        for name, data in bundle.items()
    )
print("CLI/Python parity: plan, REST bundle and MCP bundle")
PY
```
<!-- /migration:python -->

`prepare_exposure` analyzes once; `render_bundle` uses its retained sources.
The [compiler reference](../reference/compiler-api.md) covers writing, refusals
and the lower-level filesystem APIs. Already supplied in-memory data is not a
universal access-control boundary for arbitrary Python code.

## Keep permissions separate

| Managed operation | Required operator authorization | What remains separate |
| --- | --- | --- |
| Local repository analysis | `source.analyze` for the exact root | Readiness and explicit exposure selection |
| Git acquisition and analysis | `git.fetch` for the exact transport/target, plus `source.analyze` for repository/ref/subdir | Resolved commit, trust inputs and acquisition limits |
| `apizr mcp serve` | `source.analyze` for the configured local root | Explicit active MCP plugin and captured session scope |
| `apizr-oci build` | `image.build` and `registry.read` for the exact build target | Valid inputs, immutable base and Docker controls |
| `apizr-oci push` | `registry.read` and `registry.publish` for the selected image/destination | Remote identity verification and tag-conflict checks |
| `apizr-attest attest` | `registry.read`, `receipt.sign`, `timestamp.request` for the exact signing target | Key identity, expected signer and independent trust |
| `apizr-attest publish` | `registry.read` and `registry.publish` for the exact proof/destination | Verified proof bytes and remote confirmation |

Use the [complete operator examples](../reference/operator-policy.md), not a local
grant reused for a Git origin. Analyze the actual `GitSnapshot` yielded by
`acquire_snapshot`; the [Git API example](../reference/git-sources.md#python-api)
retains its acquired identity rather than authorizing a random temporary path.

Keep authority outside `apizr.toml`, user preferences and plugin locks. A project
file configures analysis and policy paths; it cannot grant permissions. With
`--project`, the operator root must match the configured repository root, not
necessarily the directory containing the TOML file.

For the [analysis MCP server](../reference/apizr-mcp-server.md), provide both
`--project` and `--operator-policy`. Its three tools cannot change the root or
choose authority. Restart the session after policy changes; this version does
not promise dynamic revocation. It remains analysis/planning only.

## Regenerate MCP servers and adapt result consumers

The stable 0.3.0 generator can emit invalid MCP structured content for non-object
returns. Updating Apizr does not modify an existing bundle. Regenerate into a new
directory, install its declared requirements, then reconnect the client to that
server. Keep the old bundle until the replacement is verified.

| Python return | 0.4 MCP `structuredContent` |
| --- | --- |
| `25.0` | `{"result": 25.0}` |
| `True` | `{"result": true}` |
| `[1, 2]` | `{"result": [1, 2]}` |
| `None` | `{"result": null}` |
| `{"total": 25.0}` | `{"total": 25.0}` |

For a tool known to return a scalar/list/null, read the `result` field. Dictionary
results are preserved, including dictionaries already containing a `result` key;
do not blindly unwrap every response. REST response bodies and direct Python
returns are unchanged. See the [result contract](../architecture/mcp-generator-v1.md#results-and-public-errors).

## Keep plugins and existing workflows explicit

From the directory containing `release/` and `core/`, export a profile and install
its locked wheels offline:

```sh
core/bin/apizr plugins catalog resolve --profile mcp --catalog release/target/catalog/catalogue.json --wheelhouse release/target/wheelhouse --output-dir mcp-plan --json
core/bin/apizr plugins lock check --project mcp-plan/apizr.toml --lock mcp-plan/apizr.plugins.lock.json --wheelhouse release/target/wheelhouse --json
core/bin/apizr plugins sync --project mcp-plan/apizr.toml --lock mcp-plan/apizr.plugins.lock.json --wheelhouse release/target/wheelhouse --plugins-dir release/plugins --json
core/bin/apizr plugins enable apizr-mcp --version 0.4.0 --plugins-dir release/plugins
```

The `oci` and `delivery` profiles follow the same resolver with their own
requirements/closures. Invoking the analysis server still requires your explicit
local project and operator policy. OCI operations require prepared Docker/Buildx;
Attest operations need the documented Attest and, for artifact transport, ORAS
binaries. Git acquisition needs Git and, for SSH, the explicit agent/trust inputs.
No tool is secretly downloaded during invocation.

Existing development `0.0.0` plugin installations, locks and operator grants are
not rewritten. New artifact hashes, versions and environment identities require
an explicitly prepared lock, activation and matching authority. Keep the old
installation until you have validated the new one.

Plugin dependencies stay outside the core. Retain your existing plugin store and
activations while checking [declared artifacts and locks](../reference/project-plugin-locks.md).
Installing another version does not activate it. Preview synchronization/updates
with their documented `--dry-run` options, then choose an explicit activation.
The catalog is not an automatic updater and supplies no operator grants.

Single-file/notebook commands and the historical YAML pipeline remain available.
The core, generated application and plugins have different dependency environments;
the `mcp` extra and the `apizr-mcp` analysis plugin are different installations.
There is no need to rewrite a working legacy pipeline into `apizr.toml`.
