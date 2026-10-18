---
title: Capture the fraud holdout with sessions and decorators
description: Track actual threshold evaluations, preserve returns and inspect the failed capture.
lesson: 10
recording: 10-sdk
---

<p class="apizr-academy-kicker">Track and review · Lesson 10</p>

# Capture the fraud holdout with sessions and decorators

The recorded lab evaluates **120 held-out synthetic rows**, using probabilities from the actual trained fraud forest. It records precision, recall and flagged volume, first for a block and then for repeated function calls.

!!! abstract "By the end of this lesson"
    - Choose a session or decorator for the unit of work you want to review.
    - Retain the evaluation file, threshold and observed metrics.
    - Check that tracking preserves normal returns and the original exception.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=Cge2-6L5cSE" data-apizr-video="Cge2-6L5cSE" data-apizr-title="Capture Python calls with sessions and decorators" aria-label="Play: Track Python calls with sessions and decorators">
    <img src="../../assets/videos/tutorial-sdk.png" width="1280" height="720" loading="lazy" alt="Academy Part X: track real Python evaluations with sessions and decorators" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Prepare the recorded holdout

Start with a fresh fraud lab from the [recorded materials](../downloads/academy-recorded-examples.zip). As in the video, train cohort A in the selected scientific environment before deriving the held-out sample:

```sh
cp data/transactions-a.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-a.json
python lab.py prepare-holdout
python lab.py source evaluate
```

`evaluation.csv` contains held-out labels and actual predicted probabilities. `thresholds.py` counts true positives, false positives and false negatives to calculate precision, recall and flagged volume. These scores depend on the sample and threshold; they are not assigned constants.

## 2. Record a block, then two ordinary calls

```sh
python lab.py source session_example
python thresholds.py session
python lab.py source tracked_evaluate
python thresholds.py calls
python lab.py history
```

The session explicitly fingerprints `evaluation.csv`, records threshold **0.5** and logs the observed metrics. The decorator selects each call's threshold and preserves its ordinary return. The recording then calls **0.35** and **0.65**.

| Recorded threshold | Precision | Recall | Flagged rows |
| --- | ---: | ---: | ---: |
| 0.5, session | 0.4857 | 0.3542 | 35 |
| 0.35, decorated call | 0.55 | 0.6875 | 60 |
| 0.65, decorated call | 0.5714 | 0.25 | 21 |

These are observations of the recorded synthetic sample. Review the full Run JSON for parameter origins rather than relying only on the teaching projection. Neither threshold is automatically the right business policy.

## 3. Check the failed capture

```sh
python lab.py source failed_review
python thresholds.py failure
python lab.py failure-check
```

The decorated function logs a partial observation and raises `ValueError`. The caller receives the same exception. The retained capture is failed and excludes the synthetic exception message. Tracking does not turn failure into success or silently retain a complete traceback.

## Practice

Use the video's exercise: replace the selected file with an in-memory array and log only an input name. Does the name identify the array's contents? What would you explicitly retain for a meaningful comparison?

??? success "Check your reasoning"

    A name alone does not fingerprint in-memory values. The recorded lesson selects a real local file and its content identity. Keep the input definition consistent across calls, choose relevant parameters and metrics explicitly, and preserve the function's normal return and exception behavior.

<span id="1-observe-a-real-return-value"></span>
<span id="2-choose-what-a-run-represents"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](jupyter.md)
