---
title: "The score moved. What else changed?"
description: Read material changes, the actual metric trade-off, self-comparison and reverse deltas.
lesson: 8
recording: 08-comparison
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 08</p>

<span id="compare-the-two-recorded-fraud-runs"></span>

# The score moved. What else changed?

The recording keeps the notebook, forest settings and seed fixed while switching between two synthetic cohorts. Their feature rows match but their fraud-label rules differ. This is a comparison-reading exercise, not an unchanged benchmark proving a better model.

!!! abstract "By the end of this lesson"
    - Read material evidence separately from observed result changes.
    - Preserve unknown evidence in self-comparison.
    - Predict B-minus-A deltas and their reverse direction.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=uu01blkTRRg" data-apizr-video="uu01blkTRRg" data-apizr-title="The score moved. What else changed?" aria-label="Play: The score moved. What else changed?">
    <img src="../../assets/videos/academy-08-youtube.jpg" width="1280" height="720" loading="lazy" alt="Lesson 08: The score moved. What else changed?" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Retain A and B from the same notebook

Start a fresh fraud lab from the [recorded materials](../downloads/academy-recorded-examples.zip). Use the same trusted scientific environment as [lesson 7](runs.md).

```sh
cp data/transactions-a.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-a.json
cp data/transactions-b.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-b.json
RUN_A=$(python -c 'import json; print(json.load(open("run-a.json"))["run_digest"])')
RUN_B=$(python -c 'import json; print(json.load(open("run-b.json"))["run_digest"])')
apizr experiment diff "$RUN_A" "$RUN_B" --format json > comparison.json
python lab.py comparison comparison.json
```

Read whether a reference matches while its content changes, whether intended and observed parameters agree, then read metric values and deltas. Unknown is a separate state, not another word for unchanged.

## 2. Interpret the trade-off actually shown

The retained recording displays these observations, rounded here exactly as its teaching projection prints them. Your Run identities and results should be read from your own environment.

| Metric | A | B | B minus A |
| --- | ---: | ---: | ---: |
| Precision | 0.48571 | 0.58333 | +0.09762 |
| Recall | 0.35417 | 0.625 | +0.27083 |
| ROC AUC | 0.68504 | 0.65485 | −0.03019 |

Precision and recall rise while AUC falls. More fundamentally, the changed label rule changes the evaluated task. These values cannot by themselves rank generalization on a fixed real-world fraud population.

## 3. Compare A with itself, then reverse the pair

```sh
apizr experiment diff "$RUN_A" "$RUN_A" --format json > self-comparison.json
python lab.py comparison self-comparison.json
apizr experiment diff "$RUN_B" "$RUN_A" --format json > reverse.json
python lab.py comparison reverse.json
```

The recorded self-comparison has zero known metric deltas, while seven material facets remain unknown. Identical record identity does not manufacture an absent runtime observation.

## Practice

Use the video's pause question: predict what reversing A and B does to a numeric delta, an input-content difference and a missing observation. Then check the actual reverse diff.

??? success "Check your reasoning"

    Comparable numeric deltas change sign. Different recorded input bytes still differ. Missing evidence stays unknown. Describe the observed trade-off and changed cohort definition; selecting a model needs a suitable evaluation protocol and error analysis beyond this diff.

<span id="1-keep-comparison-direction-explicit"></span>
<span id="2-separate-a-difference-from-its-explanation"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](model-serving.md)
