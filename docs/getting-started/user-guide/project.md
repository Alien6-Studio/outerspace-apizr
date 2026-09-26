# Configure a repository workflow

!!! warning "0.4 development — not released"

    These commands require a wheel built from the development source, not the
    published `0.3.0` package. Follow the [development installation](../../development/0.4.md#install-a-development-wheel) and record its source commit.

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

From the checkout, run:

```sh
apizr readiness --project examples/project-config/apizr.toml --report
apizr expose plan --project examples/project-config/apizr.toml --plan
mkdir -p build
apizr expose build rest --project examples/project-config/apizr.toml --output-dir build/rest
apizr expose build mcp --project examples/project-config/apizr.toml --output-dir build/mcp
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

There are no plugin, execution, output or publication settings in this format.
It loads local configuration only: it cannot install plugins, execute analyzed
code, download repositories or publish services.

## Load from Python

The loader is independent of the CLI and returns typed settings with resolved
paths. It reads only the named TOML file; callers select and load JSON policies
using the existing policy models before invoking
[the compiler API](../../reference/compiler-api.md).

```python
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
    scan_policy=settings.scan,
    graph_policy=settings.graph,
    readiness_policy=policy,
)
assert report.exit_code == 0
```

This exact Python example is also tested from the minimal installed wheel.
Loader errors are ordinary validation, decoding or filesystem exceptions; the
loader never prints results or terminates the process.

## Project plugins and operator preferences (development 0.4)

The optional `[[plugins]]` declarations identify exact wheels and requirements.
They never install, activate or execute plugins. See [project plugin locks](../../reference/project-plugin-locks.md) for the format, explicit `--user-config`, precedence and a complete installed-wheel example. Existing analysis root and policy precedence remain unchanged.
