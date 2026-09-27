# Migrate from 0.3 to 0.4

**0.4.0 is being prepared; the published stable release remains 0.3.0.**
This guide applies to the development compiler and the upcoming 0.4.0 release.
Keep the [stable Quickstart](quickstart.md) for the published 0.3.0 package.
See the [0.4.0 notes](../releases/0.4.0.md) for the complete scope and limits.

## Prepare a separate installation

Keep your existing environment and generated bundles while validating the change.
Follow [Install a development wheel](../development/0.4.md#install-a-development-wheel)
with Python 3.11–3.14, Git and uv already installed. That procedure builds a wheel,
records its source commit and installs it in a separate `core` environment outside
the checkout. Preparation can download build dependencies. The core remains minimal.

From that procedure's `$work` directory, activate the new environment:

```sh
. core/bin/activate
apizr --version
cat source-commit.txt
```

For now, the development wheel still reports `0.3.0`: the recorded commit
distinguishes it from the published package. Do not substitute a nonexistent
`outerspace-apizr==0.4.0` index installation. Official versions and artifact hashes
will be supplied by the verified release record.

## Authorize a local repository

The following example is self-contained. Start in the `$work` directory with the
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

Plugin dependencies stay outside the core. Retain your existing plugin store and
activations while checking [declared artifacts and locks](../reference/project-plugin-locks.md).
Installing another version does not activate it. Preview synchronization/updates
with their documented `--dry-run` options, then choose an explicit activation.
The catalog is not an automatic updater and supplies no operator grants.

Single-file/notebook commands and the historical YAML pipeline remain available.
The core, generated application and plugins have different dependency environments;
the `mcp` extra and the `apizr-mcp` analysis plugin are different installations.
There is no need to rewrite a working legacy pipeline into `apizr.toml`.
