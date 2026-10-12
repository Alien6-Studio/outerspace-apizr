# Compile a business project from Python

Prepare one reviewed selection and generate both interfaces through the supported
public compiler API. The result uses the same contracts and refusal rules as the
CLI, without importing your business modules during compilation.

## Before you begin

[Install Apizr](../getting-started/install.md) core in a virtual environment.
Download [business-quote.zip](../downloads/business-quote.zip), extract it outside
the checkout and open a shell in `business-quote/`. The project contains `src/`
with the quote calculation, `configure.py`, `compile.py` and both client files.
The policies grant only source analysis of that exact extracted root.

## Prepare and compile

<!-- compiler:prepare -->
```sh
python configure.py
python compile.py
```

`compile.py` uses these public operations:

```python
from apizr.compiler import prepare_exposure, render_bundle
from apizr.exposure import ExposurePolicy, ExposureRefused
from apizr.operator_policy import load_operator_policy
from apizr.repository import ScanPolicy
from apizr.repository_interfaces.output import write_bundle
from apizr.repository_readiness import RepositoryReadinessPolicy
```

It loads the exact-root grant, selects only `python:api:quote` in `ExposurePolicy`,
permits direct execution in both policies, and sets `ScanPolicy(source_roots=("src",))`.
`prepare_exposure` analyzes the project once; `render_bundle` consumes that retained
context for REST and MCP; `write_bundle` publishes into fresh sibling directories.
See the downloadable `compile.py` for the complete runnable code.

## Check the contracts before starting

```sh
python - <<'PY'
import json
from pathlib import Path
root = Path('../python-bundles')
rest = json.loads((root / 'rest/openapi.json').read_text())
assert {p for p in rest['paths'] if p.startswith('/capabilities/')} == {'/capabilities/api.quote'}
tools = json.loads((root / 'mcp/mcp-tools.json').read_text())
assert [t['name'] for t in tools['tools']] == ['api.quote']
print('Only the business quote is public')
PY
```

The generated input contract is the closed nested order shown in
[Prepare functions](functions.md). Inventory and price helpers stay private.
The independent streaming experiment is retained in source evidence.

## Handle a real refusal

The same script then deliberately selects `python:unfinished:stream_events`.
`prepare_exposure` raises `ExposureRefused`; the handler checks its structured
`diagnostics`. No partial server is published for that refused selection. A stream
cannot become a finite JSON endpoint under this policy.

A readiness report may contain non-ready unselected declarations. Exposure uses
the selected function's required evidence; it does not make unsupported declarations
eligible. The [API reference](../reference/compiler-api.md) defines other validation,
filesystem, `BundleRefused` and execution-policy failures.

## Call the result

Follow the [quote scenario](../examples/business-quote.md#start-and-call-rest),
using `../python-bundles` in place of `../bundles`. Install each emitted requirements
file in the service environment, make both real calls and verify 9,180 cents.
The clients also check the tool inventory and invalid nested input. Compilation
needs only the core; running the generated services needs their transport packages.

Both renderings reuse the retained source snapshot. A new source revision requires
a new explicit preparation; this API does not deploy, acquire Git, install plugins
or publish an image. Continue with [CI validation](../getting-started/user-guide/ci-integrations.md).
