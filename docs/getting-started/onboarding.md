---
title: Initialize and check a local project
description: Set up Apizr in your Python project, check its configuration and choose the functions to expose.
---

# Initialize and check a local project

Use `apizr init` to create a starting configuration in your own Python project,
then `apizr doctor` to check it. [Install Apizr](install.md) first. If you want
to try a complete example before configuring your project, follow the
[Quickstart](quickstart.md).

Watch the [inspection walkthrough](user-guide/inspect.md) for a project example
using `init`, `doctor`, `scan` and `inspect`.

## Initialize an existing directory

From your existing Python repository:

```sh
apizr init
apizr doctor --project apizr.toml --operator-policy .apizr/operator.json
```

Or select an existing directory and known source roots explicitly:

```sh
apizr init ./my-project --source-root src --source-root app
```

Initialization creates exactly:

```text
apizr.toml
.apizr/.gitignore
.apizr/operator.json
.apizr/policies/readiness.json
.apizr/policies/exposure.json
```

The directory must already exist. If it has an Apizr configuration, review that
configuration instead of running `init` again. Use `--source-root` to point to
folders such as `src` or `app`; Apizr does not guess your project layout.

Readiness and exposure use **direct** execution, requiring neither Docker nor a
plugin and providing no runtime isolation. Exposure enables REST/MCP formats but
**selects zero capabilities**, with `include_all_ready = false`.

The operator policy contains one `source.analyze` grant for the exact absolute
initialized root. `.apizr/.gitignore` ignores `/operator.json`; project policies
remain trackable. The root `.gitignore` is untouched. `apizr.toml` never references
operator authority and no command discovers it automatically. Pass
`--operator-policy` explicitly. After moving the project, review and explicitly
replace its local root grant.

<details markdown="1">
<summary>Initialization limits and recovery</summary>

The existing `apizr.project/v1` configuration defaults to root `.` and scan source
roots `["."]`. Explicit roots use `ScanPolicy`: duplicates normalize, overlapping
roots are refused. Up to 128 roots of 256 UTF-8 bytes each are accepted. Init
does not guess a `src/` layout, read packaging metadata, analyze source or install
plugins.

The target must exist and cannot traverse a symlink. Existing `apizr.toml`, any
`.apizr` content, or stale `.apizr-init.stage` state causes refusal. Files are
staged privately, destinations reserved exclusively and `apizr.toml` published
last. Caught failures before publication roll back owned files; an interruption
after publication preserves the complete configuration. A process crash can leave
an unaccepted `.apizr` tree or staging directory. Preserve and inspect them before
manual recovery; init refuses to merge or overwrite them. It never runs Git.

</details>

## Review, then select

```sh
apizr scan . --operator-policy .apizr/operator.json --catalog
apizr readiness --project apizr.toml --operator-policy .apizr/operator.json --report
```

`scan` takes a root directly and does not accept `--project`; pass custom roots
with repeated `--source-root`. `readiness` and `expose` load the project file.
Review capability IDs, then explicitly edit `selection.include` in
`.apizr/policies/exposure.json`. Continue with the
[repository exposure workflow](user-guide/exposure.md). Init and doctor never
select or expose capabilities.

## Check your setup {#diagnose-explicit-local-preparation}

`apizr doctor` checks the core setup by default and explains what needs attention.
An empty exposure selection is a warning until you choose your functions.
Add a profile when using a plugin; core checks always run. Use `--json` for a
machine-readable report.

| Profile | Checks |
| --- | --- |
| `core` | Supported Python, core version, project/scan schemas, accessible safe roots, configured policies and existing exact-root source admission |
| `mcp` | Explicit store, official active MCP installation, inventory binding, matching core/plugin versions and interpreter availability |
| `oci` | Official OCI installation and the same binding checks; no Docker/registry probe |
| `delivery` | Explicit BatchRequest/shared identity, evidence structure, OCI and required Attest installations, metadata-only tool/auth/trust/key references, existing authorization decisions per destination |
| `clients` | Optional YAML support; `--bundle` additionally verifies a REST bundle without generating output |

```sh
apizr doctor --project apizr.toml --operator-policy .apizr/operator.json \
  --profile mcp --plugins-dir /explicit/plugins

apizr doctor --project apizr.toml --operator-policy /explicit/operator.json \
  --profile delivery --plugins-dir /explicit/plugins \
  --delivery-request /explicit/delivery.json

apizr doctor --project apizr.toml --operator-policy .apizr/operator.json \
  --profile clients --bundle .output/rest --json
```

Plugin profiles require explicit `--plugins-dir`. An empty exposure selection or
omitted operator policy is a core warning. A supplied invalid/unauthorized policy
fails; delivery effect decisions fail without matching explicit grants.
Diagnostics identify destinations by index and omit credential, key and trust paths.

Statuses: `pass`, `warn`, `fail`, `skip`. Exit codes: **0** with no failed checks,
**1** with a failed check, **2** for invalid invocation, **130** for cancellation.
Invalid project/policy files produce fixed failed checks, never exception text.
Init returns 0 on creation, 2 on refusal and 130 on cancellation; its `--json`
success result uses `apizr.init-result/v1`.

Doctor never repairs files, creates evidence/store directories or locks, installs
dependencies, invokes plugins/tools, scans source, reads private-key/auth contents,
or contacts Docker, registries, timestamp services or the network. Local preparation
does not establish remote availability, credential validity or delivery success.
Before transfer, grant checks use the immutable build identity only as an
authorization input; they do not claim an observed registry manifest or proof.

## Shell completion

Save a script in a location you choose, then use your shell's normal loading mechanism:

```sh
apizr completion bash > /path/chosen/by/user/apizr.bash
apizr completion zsh > /path/chosen/by/user/_apizr
apizr completion fish > /path/chosen/by/user/apizr.fish
```

Apizr writes only stdout and never edits shell profiles. Completion covers modern
commands, subcommands, long options and fixed choices. File arguments use normal
shell path completion. The retained legacy generator parser does not use this completion interface.
One static command tree feeds all three adapters, with regression tests against
the actual argparse parsers. Completion never inspects projects, policies, plugin
stores, capability IDs or remote data, and never starts external tools. Scripts
contain no machine paths or timestamps.

## Python API

```python
from apizr.onboarding import doctor, initialize_project, plan_initialization

files = plan_initialization("/exact/existing/project", source_roots=("src",))
result = initialize_project("/exact/existing/project", source_roots=("src",))
report = doctor(
    project="/exact/existing/project/apizr.toml",
    operator_policy="/exact/existing/project/.apizr/operator.json",
)
```

Planning returns a pure deterministic file mapping; only the ignored operator file
contains the local root. Publication and diagnosis return typed portable results.
The core still requires only Pydantic; PyYAML remains optional through `[clients]`.
