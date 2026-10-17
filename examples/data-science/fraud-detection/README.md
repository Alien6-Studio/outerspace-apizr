# Fraud detection: one notebook, two datasets, two interfaces

Follow the [Data Scientist quickstart](../../../docs/getting-started/data-science.md)
using Apizr 0.4.6.

The notebook uses pandas, a modest Random Forest and ordinary joblib serialization.
It contains no Apizr integration. Training runs under the standard Python main
guard; importing `predict` loads no model until the first prediction and does not
train. `features.py` supplies a private feature-order helper.

`transactions-a.csv` and `transactions-b.csv` are entirely synthetic, generated
with Python's standard library by `generate_data.py`. They have identical feature
rows and different fraud-label rules, to illustrate changed recorded data and
metrics without a causal or improvement claim. There are no external datasets,
personal data or third-party data rights. These files share the repository's
GPL-3.0-or-later license.

To reproduce the committed CSV bytes:

```sh
python generate_data.py
```

`requirements.txt` pins the scientific workload independently of Apizr's core
and notebook extra. Use the quickstart's retained binary wheelhouses to reproduce
the example on a qualified Python/platform target.
