# OuterSpace Apizr

Understand and compare data-science experiments. Connect selected Python
functions to AI agents through MCP, or expose them as REST APIs.

Apizr is an **open-source capability compiler**: analyze existing Python code,
choose which functions are public, generate their interfaces, and define how
they execute. Your business logic stays in Python.

**[Data Scientist quickstart: notebook → runs → prediction](https://apizr.outerspace.sh/getting-started/data-science/)** ·
**[Quickstart: make your first MCP and REST calls](https://apizr.outerspace.sh/getting-started/quickstart/)** ·
[The full journey](https://apizr.outerspace.sh/getting-started/introduction/)

Follow [Install Apizr](https://apizr.outerspace.sh/getting-started/install/), then
the Quickstart. See the [release history](https://github.com/Alien6-Studio/outerspace-apizr/releases)
for version-specific functionality, compatibility and verified publication.
The journey is Python code → discover/select capabilities → expose as REST/MCP
→ optionally deliver as OCI.

**Apizr 0.4.5 is available on PyPI.** The core and optional MCP, OCI and Attest
plugins share the same version. See the [release record](https://apizr.outerspace.sh/releases/0.4.5/)
for functionality, verified public artifacts and installation evidence.

Python **3.11–3.14** · GPL-3.0-or-later.

**Apizr 0.4.5** lets you record and compare
experiments, then explicitly select a prediction function for REST or MCP.
Know which data, code, parameters and environment produced your result.
[Try the ordinary scikit-learn notebook](https://github.com/Alien6-Studio/outerspace-apizr/tree/v0.4.5/examples/data-science/fraud-detection).

Apizr `0.4.5` also recognizes supported Python `TypedDict` model
payloads as shared, nested JSON inputs for REST and MCP. See the
[source inspection guide](https://apizr.outerspace.sh/getting-started/user-guide/inspect/#structured-model-inputs-with-typeddict)
for an executable example and the current declaration limits.

It also adds concise MCP analysis: ask for `view="summary"`, then inspect one
function with `view="detail", capability_id="python:model:predict"`. The
[analysis server guide](https://apizr.outerspace.sh/reference/apizr-mcp-server/#start-with-a-small-view-045-development)
explains dependency evidence, pagination and localized exposure refusals.

[![PyPI version](https://img.shields.io/pypi/v/outerspace-apizr.svg?cacheSeconds=300)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml)
[![Security](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml/badge.svg?branch=master)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/security.yml)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/mkdocs.yaml/badge.svg?branch=master)](https://apizr.outerspace.sh/)
[![Python](https://img.shields.io/badge/python-3.11%E2%80%933.14-blue.svg)](https://pypi.org/project/outerspace-apizr/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)
[![OuterSpace Apizr MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr/badges/score.svg)](https://glama.ai/mcp/servers/Alien6-Studio/outerspace-apizr)
[![MCPLookup Trust Index: silver, 80 out of 100](https://mcplookup.com/badge/io.github.Alien6-Studio/outerspace-apizr?embed=a6d68610-7a46-4689-8add-e364a971ddbf)](https://mcplookup.com/badge/go/a6d68610-7a46-4689-8add-e364a971ddbf/io.github.Alien6-Studio/outerspace-apizr)

## Install with uv

With [uv](https://docs.astral.sh/uv/getting-started/installation/) and Python 3.11–3.14 installed:

```sh
uv tool install outerspace-apizr==0.4.5
```

![Install Apizr with uv](https://raw.githubusercontent.com/Alien6-Studio/outerspace-apizr/master/docs/assets/videos/uv-install.gif)

## Documentation paths

[Start here](https://apizr.outerspace.sh/start/) ·
[Examples](https://apizr.outerspace.sh/examples/) ·
[User guide](https://apizr.outerspace.sh/user-guide/) ·
[Developer guide](https://apizr.outerspace.sh/developer-guide/) ·
[Operations guide](https://apizr.outerspace.sh/operations-guide/) ·
[Reference](https://apizr.outerspace.sh/reference/)

Exposing an existing function requires no Experiment Run. The experiment path is
optional when recorded evidence helps your work. The developer guide integrates
Apizr; [Contributing](https://apizr.outerspace.sh/about/CONTRIBUTING/) covers changing Apizr itself.

## Choose your path

Have a training script or notebook? **Apizr 0.4.5** adds a
zero-execution first step:

<!-- experiment-inspection:readme -->
```sh
apizr experiment inspect train.py
```

See code, data, parameters, randomness, environment, metrics, outputs and serving
candidates. Follow the [experiment inspection example](https://apizr.outerspace.sh/getting-started/user-guide/experiment-inspection/)
for setup, notebooks and JSON. No science-framework installation is needed.

Apizr can also execute trusted workloads and keep local history.
**`run` executes your code with host filesystem, network and subprocess access;
it is not a security sandbox.** This small example uses only the standard library:

<!-- experiment-run:readme -->
```sh
cat > local_run.py <<'PY'
from pathlib import Path
mean = sum([2, 4, 6]) / 3
Path("model.json").write_text('{"mean": 4.0}\n')
PY
apizr experiment inspect local_run.py
RUN=$(apizr experiment run local_run.py --metric mean=mean --output model=model.json --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment show "$RUN"
```

Read the [local run and history guide](https://apizr.outerspace.sh/getting-started/user-guide/experiment-runs/)
for environment controls, observed evidence, failure handling and storage limits.

| Your goal | Start here |
| --- | --- |
| Understand a training script or notebook (0.4.5) | [Inspect an experiment without running it](https://apizr.outerspace.sh/getting-started/user-guide/experiment-inspection/) |
| Expose Python functions as MCP tools or REST endpoints | [Install](https://apizr.outerspace.sh/getting-started/install/) → [Quickstart](https://apizr.outerspace.sh/getting-started/quickstart/) |
| Analyze a project from an MCP client | [Install the MCP profile](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile) → [analysis server](https://apizr.outerspace.sh/reference/apizr-mcp-server/) |
| Build and deliver a service | [Install OCI or delivery](https://apizr.outerspace.sh/getting-started/install/#choose-a-plugin-profile) → [OCI](https://apizr.outerspace.sh/reference/oci-service-plugin/) and [Attest](https://apizr.outerspace.sh/reference/attest-delivery-plugin/) |
| Initialize and diagnose a project (0.4.2) | [Safe init, read-only doctor and shell completion](https://apizr.outerspace.sh/getting-started/onboarding/) |
| Validate/build in CI (0.4.2) | [GitHub Action, GitLab component source and apizr ci](https://apizr.outerspace.sh/getting-started/user-guide/ci-integrations/) |

The core handles supported static analysis and generation. Generated servers have
their own runtime dependencies. Optional plugins live in separate environments;
installation, activation and operator authorization are independent decisions.

Apizr 0.4.5 lets you expose an independent function while unrelated experiments
remain unfinished; see the [research repository example](https://apizr.outerspace.sh/getting-started/user-guide/exposure/#work-with-unfinished-research-code).



### Inspect → Run → Compare → Expose

“My ROC AUC changed. What else changed between these runs?” This core-only
example records two trusted local runs, then compares their saved evidence.

<!-- experiment-diff:readme -->
```sh
cat > compare_train.py <<'PYTHON'
max_depth = 8
score = 0.91
PYTHON
apizr experiment inspect compare_train.py
A=$(apizr experiment run compare_train.py --metric roc_auc=score --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
cat > compare_train.py <<'PYTHON'
max_depth = 12
score = 0.92
PYTHON
B=$(apizr experiment run compare_train.py --metric roc_auc=score --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment diff "$A" "$B"
rm compare_train.py
apizr experiment diff "$A" "$B" --format json > comparison.json
```

`A → B` means evidence added in B or removed from A; numeric deltas are `B - A`.
`show` reads one Run; `diff` compares two Runs from the same validated local store.
Comparison still works after deleting the source. Unknown observations remain unknown.
Apizr identifies recorded differences; it does not prove which one caused the metric change.
Read the [comparison guide](https://apizr.outerspace.sh/getting-started/user-guide/experiment-comparison/) for data, environment and output evidence.

After reviewing a successful Run, explicitly select its serving capability:

```sh
apizr experiment expose <RUN> --root . --operator-policy operator.json \
  --capability python:fraud_detection:predict --interface mcp \
  --artifact model --output-dir dist/predict
```

The current source and selected resource bytes must still match the Run.
Repository Readiness and Exposure decide eligibility. Follow the
[Experiment → serving guide](https://apizr.outerspace.sh/getting-started/user-guide/experiment-exposure/)
for source authority, exact dependency pins and current direct-service limits.

## Expose the functions you choose

<span id="one-repository-two-public-capabilities"></span>
<span id="eligibility-selection-and-interfaces"></span>

**Readiness** reports whether the available code evidence supports an interface.
An **exposure policy** names the functions you choose to make public. A **bundle**
is the generated server, its contracts and the source needed by those functions.
Being ready never makes a function public automatically.

| Connect through | Start with |
| --- | --- |
| MCP tools for agents and other clients | [Generate MCP and make two calls](https://apizr.outerspace.sh/getting-started/quickstart/#generate-the-mcp-bundle) |
| REST endpoints for applications | [Generate REST and send two requests](https://apizr.outerspace.sh/getting-started/quickstart/#use-rest-instead) |

The generated MCP server calls your selected functions. The separate,
[Apizr analysis MCP server](https://apizr.outerspace.sh/reference/apizr-mcp-server/)
analyzes repositories and plans exposure; it does not execute their functions.

## Choose execution boundaries

Analysis and generation do not execute the project. Starting a generated server
and calling its functions does: use trusted source and dependencies.
**Direct** mode runs functions inside the server. **Governed** mode uses an
**execution policy** to choose a worker and its required limits: a fresh local
process or an OCI container per call. Local workers do not isolate the host
filesystem or network; containers are not an untrusted-code guarantee.

The direct Quickstart needs no Docker. Read the
[exposure guide](https://apizr.outerspace.sh/getting-started/user-guide/exposure/)
for governed examples and the
[execution boundaries](https://apizr.outerspace.sh/architecture/governed-repository-runtime/)
for their guarantees and limits.

## Existing workflows and limits

Single-source `inspect`, `generate rest/mcp` and `execute` remain supported.
Apizr 0.4.2 also exports verified REST bundles to
[Postman, Bruno and Insomnia collections](https://apizr.outerspace.sh/getting-started/user-guide/client-collections/),
with deterministic files and safe local regeneration.

The [historical pipeline](https://apizr.outerspace.sh/getting-started/user-guide/apizr/)
is a separate compatibility path. See
[the full journey](https://apizr.outerspace.sh/getting-started/introduction/#compatibility-and-limits)
for dependency, resource and exposure limits.

[Watch the demo](https://apizr.outerspace.sh/#watch-apizr-in-action) ·
[Architecture guide](https://apizr.outerspace.sh/architecture/) ·
[Development and checks](https://apizr.outerspace.sh/getting-started/developer-guide/setup/) ·
[Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues) ·
[GPL-3.0-or-later](https://apizr.outerspace.sh/about/LICENSE/)
