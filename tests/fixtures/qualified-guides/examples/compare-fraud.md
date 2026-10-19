# Compare two fraud experiments

“My ROC AUC changed. What else changed?” Record two executions of an unchanged
notebook against different synthetic data, then separate recorded input changes
from observed result differences.

## Expected result and prerequisites

Two successful Runs retain different data/model hashes and observed metrics.
Code, hyperparameters and declared seed remain unchanged. Use Python 3.11–3.15
on qualified Linux/macOS, Apizr notebook support and the scientific requirements
provided in [fraud-detection.zip](../downloads/fraud-detection.zip).
Extract outside the checkout and open `fraud-detection/`.

The archive contains the notebook, `features.py`, requirements, generator and two
CSVs. Transactions are entirely synthetic, created by standard-library
`generate_data.py`; no real accounts or external dataset are used. Files are
GPL-3.0-or-later. Scientific packages are unnecessary for initial inspection.

## Inspect first, prepare execution next

```sh
cp data/transactions-a.csv data/transactions.csv
apizr experiment inspect fraud_detection.ipynb
```

Check Data, `n_estimators=24`, `max_depth=5`, `random_state=42`, metric signals and
`predict`. No runtime score or model is established. Follow
[the canonical preparation](../getting-started/data-science.md#prepare-to-execute-the-notebook)
to install the pinned workload into the interpreter that runs Apizr and retain
compatible wheels for serving. An isolated tool CLI does not inherit notebook packages.

## Record A and B, then compare

Run executes trusted code with host filesystem/network/subprocess access; it is
not a sandbox. Training is under the notebook's ordinary main guard.

<!-- scenario:compare -->
```sh
cp data/transactions-a.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-a.json
RUN_A=$(python -c 'import json; print(json.load(open("run-a.json"))["run_digest"])')
cp data/transactions-b.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-b.json
RUN_B=$(python -c 'import json; print(json.load(open("run-b.json"))["run_digest"])')
apizr experiment list
apizr experiment show "$RUN_B"
apizr experiment diff "$RUN_A" "$RUN_B" --format json > comparison.json
apizr experiment diff "$RUN_A" "$RUN_B"
```

## Read the recorded evidence

Both CSVs have identical feature rows and different fraud-label rules. Check
comparison Data `content_state:changed` and the separate metrics/outputs.
B replaces the active model, while A's evidence remains in history. The
[notebook walkthrough](../getting-started/data-science.md) uses these exact files;
its command blocks are executed by installed-package qualification.

Observed on macOS arm64, CPython 3.11.14 with the supplied scientific pins:

| Recorded metric | Run A | Run B |
| --- | --- | --- |
| precision | 0.4857142857142857 | 0.5833333333333334 |
| recall | 0.3541666666666667 | 0.625 |
| roc_auc | 0.6850405092592593 | 0.6548549107142857 |

The data SHA-256 changes from
`f82f5bb6e0723b2166ab5eae8566ceabc913d55522fe2adbfcb638c523cc2dae`
to `16b8f77575bd5374ad4435c04b3e9749bdaac63260d770818ed33f320c1477b0`.
These are observed example values, not a promise across other environments.

Different scores and input hashes do not establish causality, scientific quality
or a better model. Unknown facts remain unknown even when parameters agree.

## Useful failure, limits and cleanup

Trying to expose Run A while B's model is current refuses the mismatched resource.
[Share a prediction](share-prediction.md) uses B and checks this failure.
History retains JSON evidence and output identities, not model bytes or a remote
registry. Keep this directory for scenario B. Afterwards stop owned services and
remove only the extracted project/history/models and disposable sibling
wheelhouses/runtimes, after preserving needed evidence.
