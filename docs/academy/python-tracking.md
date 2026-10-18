---
title: Choose the unit you capture in Python
description: Record useful observations while preserving ordinary function behaviour.
lesson: 10
---

<p class="apizr-academy-kicker">Track and review · Lesson 10 · Plan about 25 min</p>

# Choose the unit you capture in Python

Your evaluation already runs in a Python program. You want to retain the threshold and measured result without replacing the program with a tracking server workflow.

Choose the boundary of the observation first: one block of work, or one ordinary function call. Then decide which inputs, parameters and observations are meaningful to retain.

!!! abstract "By the end of this lesson"
    - Choose a session or decorator based on the unit of work.
    - Predict which calls produce Runs and which arguments are selected.
    - Explain the limits of an input logged without file content.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=Cge2-6L5cSE" data-apizr-video="Cge2-6L5cSE" data-apizr-title="Track Python calls with sessions and decorators" aria-label="Play: Track Python calls with sessions and decorators">
    <img src="../../assets/videos/tutorial-sdk.png" width="1280" height="720" loading="lazy" alt="Academy Part X: track real Python evaluations with sessions and decorators" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 6:30 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Observe a real return value

Use Apizr 0.4.6 in the Python environment that runs this code. In a fresh working directory, run:

```python
from pathlib import Path
from apizr import tracking

measurements = [0.7, 0.8, 0.9]

@tracking.experiment(parameters=["threshold"], root=Path.cwd())
def evaluate(threshold):
    score = sum(value >= threshold for value in measurements) / len(measurements)
    tracking.log_metric("score", score)
    return score

print(evaluate(0.75))
print(evaluate(0.85))
```

The ordinary return values are two thirds and one third. Each call creates its own Run; the selected `threshold` argument is a recorded parameter. The SDK does not turn every variable into retained evidence.

## 2. Choose what a Run represents

A `tracking.session` block can cover several related operations in the same process. A decorator makes the chosen function call the capture boundary. Neither is a security boundary: the trusted workload retains its normal process access.

A selected local file can have a content identity. Logging only a name for an in-memory input does not establish that input’s bytes. The [SDK guide](../getting-started/tracking.md) shows both cases, along with exception and history behaviour.

## Practice

1. Predict the two scores before running the example, then find their Runs with `apizr experiment list`.
2. Compare them using their actual IDs. Which parameter changed, and what did your example actually select as input evidence?
3. The video evaluates thresholds on a real held-out fraud sample. Explain what additional evidence you would need before treating the tiny in-memory exercise as the same evaluation.

??? success "Check your reasoning"

    This example selects `threshold` and logs `score`. It does not call `log_input`, so no measurement file was selected.

    The selected threshold changes from `0.75` to `0.85`, and the observed fractions change accordingly. These three in-memory values do not identify the video’s held-out sample or establish a general model-quality result.

    For a file-based evaluation, explicitly select the relevant file and retain its identity. Choose observations deliberately, including their privacy implications. The SDK preserves normal returns and propagates exceptions; recording does not make a failed computation successful.

[Back to the Academy](index.md) · [Continue to the next lesson](jupyter.md)
