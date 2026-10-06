# Plan and build REST/MCP from a repository {#plan-explicit-repository-exposure}

Repository analysis requires an explicit operator policy. Save a grant for the
exact source root as `operator.json`; follow [Authorize source analysis](../../reference/operator-policy.md#authorize-repository-analysis).
This permission does not expose functions or authorize their execution.

For one Python file or notebook, use the [REST](rest.md) or [MCP](mcp.md)
single-source guide. This page covers repository-level selection and bundles.

Readiness describes eligibility under a policy. Exposure records what the
operator explicitly selects for publication, through which interfaces and under
which execution requirements. It does not generate or start a server.

An exposure plan records an explicit publication decision over static evidence; it is not an authorization grant or runtime safety proof.

## Three policies, three responsibilities

| Input | Responsibility | Backend meaning |
| --- | --- | --- |
| `--readiness-policy` | Assess static evidence and execution-contract compatibility | Which modes/controls may satisfy readiness |
| `--policy` (Exposure Policy) | Select exact public capability IDs and interfaces | Which compatible modes are permitted for this selection |
| `--execution-policy` | Configure actual invocation controls | v1 chooses local-process; v2 chooses OCI; omission chooses direct |

Readiness and exposure constrain eligibility; execution configures the boundary.
The chosen backend must appear in every selected record's compatible modes. A
mismatch refuses the whole bundle: no ranking, widening or fallback. An Exposure
Plan may permit several modes, but a generated server uses exactly one.

**READY does not mean exposed.** A helper/dependency stays private unless explicitly
selected. Planning/building records a publication decision; it does not deploy or
start the resulting service.

## Committed small examples

From the source checkout, use `examples/repository-shop` and the matching files
in [examples/policies](https://github.com/Alien6-Studio/outerspace-apizr/tree/master/examples/policies):

| Mode | Readiness | Exposure | Execution |
| --- | --- | --- | --- |
| Direct | `readiness-direct.json` | `exposure-direct.json` | Omit |
| Local | `readiness-local.json` | `exposure-local.json` | `execution-local.json` |
| OCI | `readiness-oci.json` | `exposure-oci.json` | `execution-oci.json` |

```sh
apizr expose build mcp examples/repository-shop --operator-policy operator.json --readiness-policy examples/policies/readiness-local.json --policy examples/policies/exposure-local.json --execution-policy examples/policies/execution-local.json --output-dir .output/shop-local
```

For OCI, choose the three `oci` files and add `--runtime-image sha256:<64hex>` and
`--runtime-platform linux/amd64` (or `linux/arm64`). Replace the placeholder with an
existing repository-worker image ID. The policies contain no secret or image value.
No policy stack is merged implicitly, and application dependencies are not installed.

## Choose capabilities

For `shop/pricing.py` defining `calculate`, use the exact capability ID displayed
by Scan/Readiness. Declare an interface and at least one allowed execution mode:

```sh
apizr expose plan . --operator-policy operator.json --interface mcp --execution-mode oci-container \
  --select python:shop.pricing:calculate
```

Repeat `--select`, `--interface` and `--execution-mode` for multiple choices.
Multiple compatible modes remain in the plan; there is no preferred backend.
`--all-ready` deliberately includes every repository `READY` capability.
`--exclude python:admin:delete_user` always wins over includes. Unknown include
or exclude IDs are errors, including typos in exclusions. Without any selector,
a valid empty plan is returned with a warning in the human report.

## Use policy files

Save `exposure.json`:

```json
{
  "schema_version": "apizr.exposure-policy/v1",
  "selection": {
    "include": ["python:shop.pricing:calculate"],
    "include_all_ready": false,
    "exclude": []
  },
  "interfaces": ["rest", "mcp"],
  "eligibility": {"allow_conditional": false},
  "execution": {
    "allowed": ["local-process", "oci-container"],
    "require": ["wall_timeout"]
  }
}
```

```sh
apizr expose plan . --operator-policy operator.json --policy exposure.json
apizr expose plan . --operator-policy operator.json --policy exposure.json --plan > exposure-plan.json
apizr expose plan . --operator-policy operator.json --readiness-policy readiness.json --policy exposure.json
```

Policy files use JSON. `--policy` cannot be mixed with inline exposure choices;
`--readiness-policy` remains independent. The default readiness policy is the
existing deterministic OSS policy. Its execution modes are local-process and
OCI; to plan direct execution, explicitly include `direct` in both policies:

```json
{"execution": {"modes": ["direct"], "require_controls": []}}
```

That fragment is a **readiness** policy. The exposure policy uses
`"execution": {"allowed": ["direct"]}`.

Inline flags also include `--allow-conditional` and repeated
`--require-control`. Requiring `network_deny` narrows compatible modes to OCI;
`subprocess_deny` is not advertised by the frozen v1 static backend adapters.
The additional [strict OCI profile](../../architecture/subprocess-deny.md) is
selected in the separate execution policy and verified against its worker image. Docker/image
availability is not checked. No runtime image is part of the plan.

## Read the result

The human report lists total/READY/selected/planned counts, interfaces,
contract-compatible execution counts, selected IDs, retained uncertainty and
observed support/external modules. `--plan` emits only canonical JSON on success.
The artifact binds Catalog, Graph, Repository Readiness and Exposure Policy
by digest, enabling deterministic review across filesystem locations.

- `READY` selections must still satisfy interface and execution requirements.
- `CONDITIONAL` requires explicit opt-in and an eligible shared interface
  contract. The opt-in cannot override unresolved local type/callable contracts.
- `AMBIGUOUS` and `UNSUPPORTED` are always refused.
- Globally incomplete repository evidence is always refused.
- Any refused selection blocks the whole plan. No partial result is published.

If A calls B, selecting A **does not expose B**. The plan keeps the direct
relationship as evidence. Supporting modules are observed direct requirements,
not a complete packaging closure. Effects are copied, never newly inferred or
propagated. External module names are lexical evidence without environment
resolution or package classification.

## Exit codes and bounds

| Exit | Meaning | Output |
| --- | --- | --- |
| 0 | Valid plan, including an empty plan | Human report or canonical JSON on stdout |
| 1 | Selection/evidence/policy refusal | Deterministic diagnostics on stderr; no plan bytes |
| 2 | Invalid policy, malformed ID, invalid/inaccessible repository input | Sanitized error on stderr; no plan bytes |

Argument-parser errors also exit 2. Bound discovery/graph failures that yield
incomplete evidence exit 1. All existing scan/graph bounds are available:
`--source-root`, `--exclude-dir`, file/total/entry/depth limits and AST,
relationship, call and import limits. Each source is discovered/read once;
planning does not rescan it.

## Build a direct repository bundle

Create `direct-readiness.json`:

```json
{"execution": {"modes": ["direct"]}}
```

Then build one interface for your explicitly selected eligible capabilities:

```sh
apizr expose build rest . --operator-policy operator.json --source-root src \
  --readiness-policy direct-readiness.json \
  --interface rest --execution-mode direct \
  --select python:shop.api:run --select python:shop.pricing:run \
  --output-dir .output/rest

apizr expose build mcp . --operator-policy operator.json --source-root src \
  --readiness-policy direct-readiness.json --policy direct-exposure.json \
  --output-dir .output/mcp
```

For the second example, create `direct-exposure.json` with `interfaces: ["mcp"]`,
`execution: {"allowed": ["direct"]}` and explicit selection IDs, using the
Exposure Policy format above. The target must already be permitted by the policy.
The builder cannot use the earlier OCI-only example or silently add direct mode.

REST routes and MCP Tool names include the module, such as `shop.api.run` and
`shop.pricing.run`. Only selected capabilities are public. All inspected sources
under the scanner roots are copied, including unselected helpers and modules;
use `--source-root` and `--exclude-dir` to keep tests or other code out of scope.
Unrelated bundled modules are not imported simply because they are present.

Run the generated artifacts in a prepared environment:

```sh
cd .output/rest
python -m pip install -r requirements.txt
uvicorn app:app --host 127.0.0.1 --port 8000
```

For MCP, use `python server.py --transport stdio` or
`python server.py --transport streamable-http --port 8000` from its output directory.
Transport requirements do not install your application's dependencies; provisioning
those is an explicit operator responsibility. Generation never queries or installs
them. Source/resources outside the scanned Python universe are not copied.

These servers execute trusted code directly. Global state and mutable defaults
persist across calls. Add an explicit execution policy for a fresh local worker
or OCI container per invocation, as described below.

## Use private helpers from the same repository

In the upcoming 0.4.5 release, you can organize your Python code into modules
and expose the function you choose when its local dependencies can be resolved
statically. Helpers are packaged as implementation support and stay private
unless you select them too. Published 0.4.4 retains the earlier import restriction.

For example, create this small project:

```text
project/
  features.py
  predict.py
```

```python
# features.py
def normalize(value: float) -> float:
    return value / 100
```

```python
# predict.py
from features import normalize


def predict(value: float) -> float:
    return normalize(value) * 0.8
```

Save an analysis grant for the exact `project` root in `operator.json`, as
explained at the top of this guide. Use the `direct-readiness.json` policy above:

```sh
apizr expose plan project --operator-policy operator.json \
  --readiness-policy direct-readiness.json \
  --interface rest --interface mcp --execution-mode direct \
  --select python:predict:predict

apizr expose build rest project --operator-policy operator.json \
  --readiness-policy direct-readiness.json \
  --interface rest --execution-mode direct --select python:predict:predict \
  --output-dir .output/predict-rest

apizr expose build mcp project --operator-policy operator.json \
  --readiness-policy direct-readiness.json \
  --interface mcp --execution-mode direct --select python:predict:predict \
  --output-dir .output/predict-mcp
```

Both bundles include `features.py` and `predict.py`. Only `predict.predict` is
public: send `{"value": 50.0}` to `/capabilities/predict.predict` for REST, or call
the MCP Tool `predict.predict`. REST returns `0.4`; MCP returns `{"result": 0.4}`.
Start the servers as described above, in an environment with their requirements.

The supported forms include `from features import normalize`, its stable alias,
and `import features` followed by `features.normalize(...)`. A proper package
with an empty `__init__.py` can use a uniquely resolved relative import. Ambiguous,
star, rebound, dynamic and unresolved external imports remain refused. Required
helper bindings and module initialization must also have sufficient evidence.
A nonempty package initializer without callable Readiness evidence remains
conditional, even when it contains only a docstring. Private helpers do not need
their own public JSON input contract. Their effects are not inferred or propagated.

Single-file generation remains conservative because it has no repository evidence.
`--allow-conditional` does not waive unresolved interface contracts. Repository
bundles still copy the complete inspected source universe and refuse globally
incomplete evidence; they do not compute a transitive dependency closure.
See [Repository Readiness](../../architecture/repository-readiness-v1.md#resolved-local-import-refinement)
for the retained import evidence and its limits.

Build exits 0 on success, 1 on exposure/bundle refusal, and 2 on invalid or
operational input. A valid empty Exposure Plan is refused for a server build.
The output must be new or empty: staging and atomic publication prevent partial
bundles and overwriting existing contents. There is no saved-plan CLI shortcut.

See [Repository Bundle v1](../../architecture/repository-bundle-v1.md) for exact
integrity, packaging and runtime semantics, and
[Exposure Plan v1](../../architecture/exposure-plan-v1.md) for planning contracts.


## Build a governed repository bundle

Use an exposure policy whose `execution.allowed` explicitly includes the requested
backend for every selection. The readiness policy must also allow it. For local
execution, create `local-policy.json` containing `{}` and use:

```bash
apizr expose build mcp . --operator-policy operator.json \
  --readiness-policy readiness.json --policy exposure.json \
  --execution-policy local-policy.json --output-dir .output/mcp
```

For example, the readiness execution configuration is
`{"execution":{"modes":["local-process"]}}` and the exposure execution configuration
is `{"execution":{"allowed":["local-process"]}}`. Keep your explicit selection and
`interfaces: ["mcp"]` in the exposure policy.

For OCI, allow `oci-container` in those policies, create `oci-policy.json` containing
`{"schema_version":"apizr.execution/v2"}`, and supply an existing image ID/platform:

```bash
apizr expose build mcp . --operator-policy operator.json \
  --readiness-policy readiness.json --policy exposure.json \
  --execution-policy oci-policy.json \
  --runtime-image sha256:<64hex> --runtime-platform linux/amd64 \
  --output-dir .output/mcp
```

Replace the image placeholder with the immutable image ID. It must advertise
`org.apizr.repository.worker.protocol=apizr.repository-runtime/v1` as well as the
existing single-source worker label. No image is pulled automatically. Generation
is static and works without Docker; the generated server checks availability at
startup and invocation. CLI output describes the **configured** backend.

Use `rest` and a REST exposure policy for the corresponding HTTP server. Install
the emitted requirements and start generated servers as in the direct examples.
The transport never imports project source. Each call revalidates all artifacts
and copies the exact Python source universe into a fresh worker directory.
Globals, mutable defaults and support-module state reset on every governed call;
direct servers keep their existing persistent-state behavior.

Local workers provide timeout/bounds/environment/process cleanup, not a filesystem
or network sandbox. OCI adds the established container controls and requires the
repository-aware image. Local execution cannot prohibit subprocesses. OCI offers an opt-in
[strict subprocess-deny profile](../../architecture/subprocess-deny.md), and OCI
is not a VM. Missing backends refuse operation without fallback. Application
libraries must be installed in the execution Python environment or selected image;
no dependency installation/inference or resource-file packaging is added.

See [Governed repository execution](../../architecture/governed-repository-runtime.md)
for contracts, tamper validation, error mappings and deployment responsibilities.

## Client collections

Apizr can export the retained REST bundle to
[Postman, Bruno and Insomnia collections](client-collections.md), with deterministic
files and safe local regeneration. No source scan or execution is needed.
