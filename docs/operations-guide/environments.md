# Prepare environments and permissions

Install the components needed for a selected workflow and grant its exact
operation. The result is a reviewed environment plan with no implied authority.

## Before you begin

Use [Install Apizr](../getting-started/install.md) as the canonical procedure.
Core Python support is 3.11–3.14. Release dependency exports qualify Linux x86-64
3.11–3.14 and macOS arm64 3.11/3.14; Homebrew runtime is qualified on Apple Silicon.
Windows and Intel macOS Homebrew runtime are not qualified by those exports.

## Assign dependencies to an environment

| Environment | Needed when | Inputs |
| --- | --- | --- |
| Core CLI/compiler | Analysis and generation | Public core; notebook/clients extra only for those workflows |
| Scientific workload | Trusted experiment execution | Core plus notebook/workload requirements in that interpreter |
| Each extension | Analysis MCP, OCI build/push or Attest | Verified wheel and exact locked closure; separate plugin store |
| Generated service | Client invocation | Generated transport requirements and explicit application pins |
| Governed worker image | OCI per-call execution | Prepared trusted repository-worker image and runtime dependencies |

`pipx` and `uv tool` isolate a CLI. They do not see an existing notebook kernel's
pandas installation. Use the workload interpreter for Run. Plugin environments
are also separate from the generated service; enabling OCI does not install
Docker or service libraries.

## Install, activate, authorize

Install the exact core/plugin versions and profiles using the installation guide.
List the inventory, then activate only a selected version. For source reads, grant
`source.analyze` on the exact local root. `apizr init` writes a local operator file;
review it before passing it explicitly to `doctor` or repository commands.

| Action | Minimum documented rights |
| --- | --- |
| Analyze an explicit repository root | `source.analyze` |
| Acquire one reviewed Git revision | Separate `git.fetch` plus source grant for that snapshot |
| Build one direct service image | `image.build`, `registry.read`, exact base/inputs/platform/tag/plugin identity |
| Push one built image to one repository | `registry.read`, `registry.publish` for that repository/plugin identity |
| Sign one delivery | `registry.read`, `receipt.sign`, `timestamp.request`, exact key/signer/TSA |
| Verify an existing receipt offline | Independent public trust; no private signing key |

The [operator reference](../reference/operator-policy.md) has the complete grant
formats. No example requires granting every permission. Project declarations never
grant authority or auto-activate plugins. Directly invoked trusted programs remain
outside managed permission checks; these checks are not a universal OS sandbox.

## Check before operation

```sh
apizr --version
apizr doctor --project apizr.toml --operator-policy .apizr/operator.json
```

Use the initialized project from [onboarding](../getting-started/onboarding.md).
Doctor is read-only and reports configuration/availability. It does not prove
registry credentials, service health or signing success. Check those through the
selected operation, then continue with [a local service](local-service.md).
