---
title: From a notebook to a prediction service
description: Inspect an ordinary scikit-learn notebook, compare two recorded runs, and expose its prediction function through REST and MCP.
---

# From a notebook to a prediction service

Know which data, code, parameters and environment produced your result, compare
experiments, then turn the useful Python capability into MCP or REST.

This guide uses **public Apizr 0.4.5 packages**. The full notebook → Run →
comparison → REST/MCP journey passed from fresh PyPI installations outside the
checkout. See the [release verification](../releases/0.4.5.md#public-installation).

The [fraud detection example](https://github.com/Alien6-Studio/outerspace-apizr/tree/v0.4.5/examples/data-science/fraud-detection)
is an ordinary notebook: pandas, a small scikit-learn forest, three metrics and
joblib model serialization. It has no Apizr import, decorator or tracking call.
Keep the notebook unchanged throughout this guide. Only the active CSV changes
between the two runs.

## Prepare your environment

Already using pandas and scikit-learn? Install Apizr's notebook support
into that same Python environment. Apizr does not provide a science extra or
install scientific packages as core dependencies.

For this exact reference example, use Python 3.11–3.14 on macOS or Linux and a
fresh virtual environment. Copy the example outside the Apizr checkout and open
a shell in `fraud-detection/`. Download compatible public wheels once; the
serving steps reuse them without resolving a different dependency set.

```sh
python3 -m venv ../science
. ../science/bin/activate
export TARGET="$PWD/../apizr-runtime"
export SCIENCE_WHEELHOUSE="$PWD/../science-wheels"
mkdir -p "$TARGET/base" "$TARGET/extras"
python -m pip download --index-url https://pypi.org/simple --only-binary=:all: \
  'outerspace-apizr[notebook,http,mcp]==0.4.5' -d "$TARGET/base"
python -m pip download --index-url https://pypi.org/simple --only-binary=:all: \
  -r requirements.txt -d "$SCIENCE_WHEELHOUSE"
python -m pip install --no-index --find-links "$TARGET/base" \
  'outerspace-apizr[notebook,http,mcp]==0.4.5'
python -m pip install --no-index --find-links "$SCIENCE_WHEELHOUSE" -r requirements.txt
cp data/transactions-a.csv data/transactions.csv
export BUNDLES="$PWD/../prediction-bundles"
```

Downloads and installation are preparation time. The product journey below
starts with inspection in the prepared environment. All subsequent dependencies
come from the retained wheelhouses; neither dataset requires a download.

## 1. Inspect without running

<!-- science:inspect -->
```sh
apizr experiment inspect fraud_detection.ipynb
```

The report shows **Code, Data, Parameters, Randomness, Environment, Metrics,
Outputs and Serving**. Look for `data/transactions.csv`, `n_estimators = 24`,
`max_depth = 5`, `random_state = 42`, the three metric calls and `predict`.
Metric values and the saved model do not exist yet. Inspection does not execute
the notebook; a seed records an intended control, not a determinism guarantee.

Excerpt from the reference notebook's inspection:

```text
Parameters — CAPTURED
  n_estimators = 24 (cell 1, line 7)
  max_depth = 5 (cell 1, line 8)
  Static candidates, not runtime parameters.
```

## 2. Record Run A

Run executes trusted code with host filesystem, network and subprocess access.
It is not a security sandbox. Review unfamiliar notebooks before executing them.

<!-- science:run-a -->
```sh
apizr experiment run fraud_detection.ipynb \
  --output model=artifacts/model.joblib --format json > run-a.json
RUN_A=$(python -c 'import json; print(json.load(open("run-a.json"))["run_digest"])')
```

The worker captures the three metrics automatically. The explicit output name
`model` makes the later artifact selection readable. `artifacts/trained.txt`
marks that training executed; it is not selected for serving.

## 3. Change the data, then record Run B

<!-- science:run-b -->
```sh
cp data/transactions-b.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb \
  --output model=artifacts/model.joblib --format json > run-b.json
RUN_B=$(python -c 'import json; print(json.load(open("run-b.json"))["run_digest"])')
```

Both committed CSVs are synthetic transactions. B uses a different fraud-label
rule over the same features. Neither cohort describes real people or accounts.
The notebook, hyperparameters and seed remain unchanged.

## 4. Find both runs

<!-- science:list -->
```sh
apizr experiment list
```

## 5. Review Run B

<!-- science:show -->
```sh
apizr experiment show "$RUN_B"
```

Read the recorded input and model hashes, worker Python/package versions,
parameters and observed metrics. History retains A even though B has replaced
the active CSV and model. Only selected runtime facts are collected.

## 6. Compare A and B

<!-- science:diff -->
```sh
apizr experiment diff "$RUN_A" "$RUN_B"
```

The recorded data identity and observed metrics changed. This comparison does
not establish that one caused the other. The source, parameters, seed and
environment specification should agree; unknown observations remain unknown.

## 7. Select the prediction from Run B

Explicitly choose the Run, capability, model artifact and serving dependencies.
`predict` needs joblib and scikit-learn; pandas is used only during training.

The wheelhouse supplies evidence that the selected, versioned distributions
provide the external imports. Apizr inspects wheel members without importing
them. `--allow-conditional` acknowledges that external code remains opaque:
wheel membership does not prove safe initialization or successful invocation.
Missing, ambiguous or unsupported required dependencies still block exposure.

Authorize reading this local example with a narrowly scoped operator file:

<!-- science:authority -->
```sh
python - <<'PY'
import json
from pathlib import Path
Path("operator.json").write_text(json.dumps({
    "schema": "apizr.operator-policy/v1",
    "grants": [{"adapter": "repository", "operation": "analyze",
                "target": {"kind": "local", "root": str(Path.cwd())},
                "permissions": ["source.analyze"]}]
}))
PY
CAPABILITY=python:fraud_detection:predict
```

## 8. Generate REST

<!-- science:rest-expose -->
```sh
apizr experiment expose "$RUN_B" --root . --operator-policy operator.json \
  --capability "$CAPABILITY" --interface rest --artifact model \
  --dependency scikit-learn --dependency joblib \
  --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional \
  --output-dir "$BUNDLES/rest"
```

Prepare a separate serving environment from the generated requirements and
retained wheels. Its application pins come from Run B, without a new resolution
against a package index:

<!-- science:rest-install -->
```sh
python -m venv ../serving
export SERVING_PYTHON="$PWD/../serving/bin/python"
"$SERVING_PYTHON" -m pip install --no-index \
  --find-links "$TARGET/extras" --find-links "$TARGET/base" \
  --find-links "$SCIENCE_WHEELHOUSE" \
  -r "$BUNDLES/rest/requirements.txt" -r "$BUNDLES/rest/application-requirements.txt"
```

## 9. Start REST and make a real call

<!-- science:rest-start -->
```sh
export REST_PORT=${REST_PORT:-8765}
"$SERVING_PYTHON" -m uvicorn --app-dir "$BUNDLES/rest" app:app \
  --host 127.0.0.1 --port "$REST_PORT" > "$BUNDLES/rest.log" 2>&1 &
REST_PID=$!
echo "$REST_PID" > "$BUNDLES/rest.pid"
```

<!-- science:rest-call -->
```sh
python - <<'PY'
import json, os, time
from urllib.request import Request, urlopen
base = "http://127.0.0.1:" + os.environ["REST_PORT"]
deadline = time.monotonic() + 20
while True:
    try:
        with urlopen(base + "/health", timeout=1) as response:
            assert json.load(response) == {"status": "ok"}
        break
    except OSError:
        if time.monotonic() >= deadline:
            raise
        time.sleep(0.05)
payload = {"transaction": {"amount": 845.0, "transaction_velocity": 11,
                           "foreign_transaction": True, "account_age_days": 45}}
with urlopen(Request(base + "/capabilities/fraud_detection.predict",
                     data=json.dumps(payload).encode(),
                     headers={"Content-Type": "application/json"}), timeout=10) as response:
    print(json.dumps(json.load(response)))
PY
```

The response contains `predictions`, with a classification and probability.
Only `predict` is public. Training and the private feature helper are not routes.

## 10. Generate MCP from the same Run

<!-- science:mcp-expose -->
```sh
apizr experiment expose "$RUN_B" --root . --operator-policy operator.json \
  --capability "$CAPABILITY" --interface mcp --artifact model \
  --dependency scikit-learn --dependency joblib \
  --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional \
  --output-dir "$BUNDLES/mcp"
"$SERVING_PYTHON" -m pip install --no-index \
  --find-links "$TARGET/extras" --find-links "$TARGET/base" \
  --find-links "$SCIENCE_WHEELHOUSE" \
  -r "$BUNDLES/mcp/requirements.txt" -r "$BUNDLES/mcp/application-requirements.txt"
```

## 11. Call it with the official MCP client

<!-- science:mcp-call -->
```sh
python - <<'PY'
import json, os
import anyio
from mcp import Client, StdioServerParameters
async def main():
    async with Client(StdioServerParameters(
        command=os.environ["SERVING_PYTHON"],
        args=[os.path.join(os.environ["BUNDLES"], "mcp/server.py")],
    ), read_timeout_seconds=20) as client:
        tools = await client.list_tools()
        assert [tool.name for tool in tools.tools] == ["fraud_detection.predict"]
        result = await client.call_tool("fraud_detection.predict", {
            "transaction": {"amount": 845.0, "transaction_velocity": 11,
                            "foreign_transaction": True, "account_age_days": 45}})
        assert not result.is_error
        print(json.dumps(result.structured_content))
anyio.run(main)
PY
```

The MCP client initializes a real stdio session and receives the same structured
business result as REST. This generated prediction service is separate from the
optional Apizr analysis MCP plugin.

Stop the REST process when finished:

```sh
kill "$REST_PID"
```

A successful Run is evidence, not production approval. A saved model is an
ordinary artifact, not a registry entry. Exposure makes an explicitly chosen
interface; organizational promotion and deployment remain separate decisions.
Continue with [experiment evidence](user-guide/experiment-runs.md),
[comparison](user-guide/experiment-comparison.md) or
[serving integrity](user-guide/experiment-exposure.md).
