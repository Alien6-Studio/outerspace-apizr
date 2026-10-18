---
title: Inspect a notebook without inventing results
description: Tell source evidence from values observed during execution.
lesson: 6
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 06 · Plan about 20 min</p>

# Inspect a notebook without inventing results

A notebook contains a call to `roc_auc_score` and a setting called `learning_rate`. Has the model achieved a particular score, and did the workload actually use that setting?

The distinction is the heart of this lesson: recognizing a declaration or call is useful evidence, but observing its runtime value is a different operation.

!!! abstract "By the end of this lesson"
    - Read static candidates, selected file identities and unresolved inputs.
    - Recognize which metric values remain unobserved.
    - Explain a change in input identity without running training.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=9P5F42RYCRs" data-apizr-video="9P5F42RYCRs" data-apizr-title="Inspect a machine learning notebook without running it" aria-label="Play: Inspect a machine learning notebook without running it">
    <img src="../../assets/videos/tutorial-experiment-inspection.png" width="1280" height="720" loading="lazy" alt="Academy Part VI: inspect experiment evidence before training" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 5:54 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Inspect an intentionally incomplete example

Create these files in a fresh directory:

```sh
printf 'amount,fraud\n10,0\n' > train.csv
cat > example.py <<'PYTHON'
import pandas as pd
from sklearn.metrics import roc_auc_score
learning_rate = 0.05
training = pd.read_csv("train.csv")
validation = pd.read_csv(DATA_PATH)
roc_auc_score(labels, predictions)
PYTHON
apizr experiment inspect example.py
```

Inspection can complete without importing pandas or executing the file. `train.csv` can be identified by its bytes. `DATA_PATH` remains unresolved. The literal learning-rate setting is a candidate, and the metric call is recognized without an observed score.

## 2. Read the report as separate questions

The eight sections cover code, data, parameters, randomness, environment, metrics, outputs and serving. A section marked `captured` describes that section’s evidence; it is not an overall reproducibility certificate.

For example, source inspection cannot borrow the inspector’s installed scikit-learn version and present it as the notebook’s observed training environment. An existing model file is not automatically an observed output of training.

## Practice

1. Inspect the example and locate the known input, the unresolved data reference and the unobserved metric.
2. Change the CSV row from `10,0` to `20,1` and inspect again. Compare its content fingerprint.
3. Explain whether a changed data fingerprint establishes that a training run used the new row. Then follow the [fraud notebook inspection](../getting-started/user-guide/experiment-inspection.md) to apply the same reasoning to the video’s larger example.

??? success "Check your reasoning"

    The CSV’s content identity changes even though its path is unchanged. Inspection still has not executed training, so it cannot establish a score or which rows a runtime computation consumed.

    The unresolved input remains unresolved. Keep that uncertainty in your explanation instead of turning a successful inspection command into an unsupported claim about data completeness or scientific reproducibility.

[Back to the Academy](index.md) · [Continue to the next lesson](runs.md)
