# Configure a repository workflow

For prerequisites and package availability, see [Install Apizr](../install.md).

Use `--project` to share readiness and exposure settings in a versioned
`apizr.toml`. Apizr never searches for or loads this file automatically.
Existing commands without `--project` and the historical pipeline's YAML
`--configuration` option retain their behavior.

## Complete example

The checkout contains a small, runnable example in
[`examples/project-config`](https://github.com/Alien6-Studio/outerspace-apizr/tree/master/examples/project-config):

```text
project-config/
  apizr.toml
  policies/readiness.json
  policies/exposure.json
  src/calculator.py
```

`src/calculator.py` defines `add(a: int, b: int = 1) -> int`.
The project file contains:

```toml
schema_version = "apizr.project/v1"
root = "."
readiness_policy = "policies/readiness.json"
exposure_policy = "policies/exposure.json"

[scan]
source_roots = ["src"]
excluded_directories = ["ignored"]
max_file_bytes = 4096

[graph]
max_ast_nodes = 10000
```

`policies/readiness.json` selects the existing direct readiness contract:

```json
{"execution": {"modes": ["direct"]}}
```

`policies/exposure.json` explicitly selects one capability and both interfaces:

```json
{
  "selection": {"include": ["python:calculator:add"]},
  "interfaces": ["rest", "mcp"],
  "execution": {"allowed": ["direct"]}
}
```

From the checkout, prepare a separate operator grant. Review its root before use;
authority never belongs in `apizr.toml`.

```sh
python3 - <<'PYTHON'
import json
from pathlib import Path
root = str(Path("examples/project-config").resolve())
Path("project-operator.json").write_text(json.dumps({"schema":"apizr.operator-policy/v1","grants":[{"adapter":"repository","operation":"analyze","target":{"kind":"local","root":root},"permissions":["source.analyze"]}]}))
PYTHON
```

Then run:

```sh
apizr readiness --project examples/project-config/apizr.toml --operator-policy project-operator.json --report
apizr expose plan --project examples/project-config/apizr.toml --operator-policy project-operator.json --plan
mkdir -p build
apizr expose build rest --project examples/project-config/apizr.toml --operator-policy project-operator.json --output-dir build/rest
apizr expose build mcp --project examples/project-config/apizr.toml --operator-policy project-operator.json --output-dir build/mcp
```

The output directories must be absent or empty. Generating these bundles needs
only the base installation; running them requires their transport dependencies.
The installed-wheel test copies this exact example outside the checkout and
compares all four commands with their explicit-argument equivalents.

## Paths and precedence

`root`, `readiness_policy` and `exposure_policy` are relative to the directory of
the file named by `--project`, including when invoked from another directory.
Absolute local paths are also accepted. No environment-variable or `~` expansion
is performed, and URI paths are rejected. `scan.source_roots` retains its existing
meaning: paths inside the repository identified by `root`.

| Setting | Resolution |
| --- | --- |
| Repository root | Explicit positional root overrides the file; the file defaults to `.` relative to its directory |
| Scan and graph bounds | Explicit CLI values override the file, even when equal to the usual parser default; omitted values retain existing model defaults |
| Source roots | Repeated CLI `--source-root` values replace the file's `scan.source_roots` |
| Directory exclusions | Standard exclusions, file `excluded_directories`, and repeated CLI `--exclude-dir` values are combined, preserving additive exclusion behavior |
| Readiness policy | `readiness --policy` or `expose --readiness-policy` replaces the file's `readiness_policy` |
| Exposure policy | `expose --policy` replaces the file's `exposure_policy` as a whole |
| Output and execution | Always explicit CLI options; they cannot be configured in the project file |

CLI paths, including a positional root, policy overrides and `--output-dir`,
remain relative to the current working directory. Overridden policy paths from
the project file are not opened. The project file itself must still be valid.

A selected exposure policy file remains incompatible with inline exposure
choices (`--select`, `--exclude`, `--all-ready`, `--interface`, `--execution-mode`,
`--require-control`, `--allow-conditional`). This also applies when the policy
path comes from `apizr.toml`: conflicting choices are refused, never merged.
To use inline choices, use a project file without `exposure_policy`.
Readiness, exposure and execution policies remain independent; no selection,
execution mode or permission is implicitly widened.

## Supported settings

`schema_version` is required and must equal `apizr.project/v1`. `root` defaults
to `.`; the two policy paths are optional. The `[scan]` and `[graph]` tables reuse
`ScanPolicy` and `GraphPolicy`, including their existing validation and bounds.
Scan settings include source roots, excluded directories, file/total byte limits,
source-file count, entry count and depth. Graph settings include AST-node,
relationship, call and import limits. Existing fixed schema versions, Python-only
suffixes and skipped symlinks remain unchanged.

The UTF-8 TOML file is limited to **64 KiB**. Unknown fields or versions, invalid
TOML, wrong types and invalid bounds are rejected. Strings, booleans and floats
are not converted into integer bounds. The CLI reports these as invalid input
with exit code 2, preserving its existing error presentation.

There are no execution, output or publication settings in this format.
It loads local configuration only: it cannot install plugins, execute analyzed
code, download repositories or publish services.

## Load from Python

The loader is independent of the CLI and returns typed settings with resolved
paths. It reads only the named TOML file; callers select and load JSON policies
using the existing policy models before invoking
[the compiler API](../../reference/compiler-api.md).

```python
from pathlib import Path
from apizr.operator_policy import load_operator_policy
from apizr.compiler import assess_readiness
from apizr.project import load_project
from apizr.repository_readiness import RepositoryReadinessPolicy

settings = load_project("examples/project-config/apizr.toml")
assert settings.readiness_policy is not None  # Present in this example.
policy = RepositoryReadinessPolicy.model_validate_json(
    settings.readiness_policy.read_bytes()
)
report = assess_readiness(
    settings.root,
    operator_policy=load_operator_policy(Path("project-operator.json")),
    scan_policy=settings.scan,
    graph_policy=settings.graph,
    readiness_policy=policy,
)
assert report.exit_code == 0
```

This exact Python example is also tested from the minimal installed wheel.
Loader errors are ordinary validation, decoding or filesystem exceptions; the
loader never prints results or terminates the process.

<span id="project-plugins-and-operator-preferences-development-04"></span>

## Project plugins and operator preferences

The optional `[[plugins]]` declarations identify exact wheels and requirements.
They never install, activate or execute plugins. See [project plugin locks](../../reference/project-plugin-locks.md) for the format, explicit `--user-config`, precedence and a complete installed-wheel example. Existing analysis root and policy precedence remain unchanged.

## Application dependencies and resources (0.4.1 development)

This optional table extends the existing `apizr.project/v1` configuration. It is
available in development builds of all four coordinated **0.4.1rc1** distributions;
it is not part of the published 0.4.0rc1 packages.

```toml
[application]
dependencies = ["six==1.17.0"]
resources = ["data/message.txt"]
```

The complete executable fixture is
[`examples/application-inputs`](https://github.com/Alien6-Studio/outerspace-apizr/tree/release/0.4.1/examples/application-inputs).
Use the commands above with `examples/application-inputs/apizr.toml` and a
`source.analyze` grant rooted at that example. Its selected `formatter.message`
capability reads `data/message.txt` using `__file__`, decodes it with Six and
returns **`PORTABLE CAFÉ`**. The installed OCI qualification builds both transports,
removes the project and generated bundles, then invokes REST and MCP with no
source mounts. Run that existing qualification from a development checkout:

```sh
uv run --locked python scripts/smoke_oci_plugin.py --work-dir /tmp/apizr-application-proof --docker-socket /var/run/docker.sock
```

Use a fresh work directory and the actual Docker socket on your system. Test
preparation explicitly obtains wheels; analysis never does so.

| Dependency group | Installation boundary |
| --- | --- |
| Core | Minimal Apizr environment; unchanged by application declarations |
| Plugins | Existing isolated, locked plugin environments |
| Application | Generated service environment, with the transport server closure |

Dependency declarations accept a bounded exact `name==version` subset: numeric
release versions with optional epoch, prerelease (`a`, `b`, `rc`), post/dev and
lowercase local version components. Names normalize to lowercase with `.`, `_`
and `-` runs replaced by `-`. Entries sort by normalized name; duplicate names
are errors even when versions agree. Ranges, extras, markers, direct URLs, local
projects, options and wildcard versions are unsupported. No resolver or import
inference runs in Apizr analysis. The existing OCI path consumes an explicitly
prepared wheelhouse and hashed lock, verifies the exact server/application
closure offline, and installs it only in the service image.

Resources are explicit regular files relative to the permitted project root,
independent of scan source roots. Paths normalize and sort deterministically.
Absolute paths, `..`, backslashes, hidden components, control characters,
symlinks (including parents), directories, missing files and duplicate normalized
paths or filesystem identities are refused. Limits are 128 pins, 128 files,
16 MiB per file and 32 MiB of resource contents in total. Files retain their
project-relative paths under `source/`, together with Python source paths, so
ordinary paths derived from `__file__` continue to work. Resource/source path
collisions are refused. There is no recursive directory inclusion or content-based
secret detection: explicitly declaring a visible file can disclose its contents.
Undeclared `.env`, credentials, hidden files and unrelated data are not resources.

Both existing REST/MCP manifests and `repository-interface.json` carry optional
`application` metadata: normalized pins, resource paths, sizes and SHA-256 digests,
and the analyzed repository digest. `application-requirements.txt` carries only
application pins; `requirements.txt` remains server-only. Existing artifact digests
and OCI input identities bind these bytes. Changing a declared dependency/resource
changes the bundle and build identity; unrelated data does not. Python files in
scan roots remain part of the existing source catalog, independently of resources.
This is an optional bundle extension, not a delivery/publication manifest.

Projects omitting the table (or leaving both lists empty) keep their previous
layout and need no new metadata fields. `source.analyze` and `git.fetch` remain
independent authorizations. Capturing resources never imports code, installs or
downloads packages. Existing readiness eligibility is unchanged: a dependency
pin does not make an otherwise ineligible function exposable. This fixture uses
an eligible façade and a helper with a lazy third-party import. The first increment
supports direct REST/MCP services and their OCI images; governed per-call worker
bundles, package metadata/resource APIs and arbitrary installed-project layouts
are outside this contract. A resource capture is bounded and checks individual
file changes; it is not an atomic snapshot of a mutable local filesystem.
