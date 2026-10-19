# Share a prediction from a reviewed Run

Expose Run B's prediction for an application and an MCP client, keeping training
and feature helpers private.

## Expected result and prerequisites

REST and MCP return the same `predictions` object. Invalid nested input is refused.
Complete [Compare fraud experiments](compare-fraud.md); retain Run B, the unchanged
notebook, matching `artifacts/model.joblib` and scientific wheels. The
[complete environment procedure](../getting-started/data-science.md) defines
`TARGET`, `SCIENCE_WHEELHOUSE`, `BUNDLES` and `SERVING_PYTHON`, including the
separate serving runtime. Files/data are the synthetic GPL-3.0-or-later example.

## Select the function, model and libraries

Prepare the [exact-root grant](../getting-started/data-science.md#7-select-the-prediction-from-run-b),
then build:

<!-- scenario:prediction -->
```sh
RUN_B=$(python -c 'import json; print(json.load(open("run-b.json"))["run_digest"])')
CAPABILITY=python:fraud_detection:predict
apizr experiment expose "$RUN_B" --root . --operator-policy operator.json \
  --capability "$CAPABILITY" --interface rest --artifact model \
  --dependency scikit-learn --dependency joblib \
  --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional \
  --output-dir "$BUNDLES/rest"
apizr experiment expose "$RUN_B" --root . --operator-policy operator.json \
  --capability "$CAPABILITY" --interface mcp --artifact model \
  --dependency scikit-learn --dependency joblib \
  --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional \
  --output-dir "$BUNDLES/mcp"
```

Conditional opt-in acknowledges opaque external wheel providers; it does not
waive required evidence or unsupported contracts. pandas remains a training
library; joblib and scikit-learn are explicit selected serving dependencies.

## Make and check real calls

Install both generated requirements files and start REST using
[steps 8–9](../getting-started/data-science.md#8-generate-rest). Send:

```json
{"transaction":{"amount":845.0,"transaction_velocity":11,"foreign_transaction":true,"account_age_days":45}}
```

Read classification/probability in `predictions`. The
[complete MCP client](../getting-started/data-science.md#11-call-it-with-the-official-mcp-client)
initializes a real stdio session, asserts exactly `fraud_detection.predict` and
calls the same payload without an AI account. Qualification compares both actual
responses and checks private training/helpers. `artifacts/trained.txt` is not a
selected service resource.

The qualified macOS arm64 / Python 3.11.14 execution returned this actual object
through both transports:

```json
{"predictions":[[1,0.8127568160788873]]}
```

The label is `1` for this synthetic transaction, with the example model's reported
probability. This is a model result, not a calibrated real-world risk estimate.

## Useful failures

Missing `amount`, a string amount or an extra transaction field produce HTTP 422
and MCP tool errors. Run A with B's current model must fail before publishing a
bundle. Restore exact reviewed bytes or record another legitimate Run; do not
relabel or disable an identity check.

## Limits and cleanup

Resource bounds are 16 MiB per file / 32 MiB combined. Current Run-bound resources
use direct service bundles, not governed per-call workers. A working prediction
is neither scientific validation nor deployment approval. Stop REST with
`kill "$REST_PID"`; MCP closes with its client context. Remove only the example's
generated bundles/runtimes after preserving any evidence needed.
