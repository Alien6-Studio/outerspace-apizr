---
title: Compare Runs and interpret a metric delta
description: Describe observed differences without claiming they caused an improvement.
lesson: 8
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 08 · Plan about 25 min</p>

# Compare Runs and interpret a metric delta

Two Runs have different scores. Before calling the second model better, ask what else changed: the data, the label rule, parameters, code, environment or selected outputs.

The video compares two cohorts from the synthetic fraud example. Its changed label rules are part of the lesson: a metric increase alone does not establish better generalization.

!!! abstract "By the end of this lesson"
    - Interpret A-to-B and B-to-A comparisons consistently.
    - Connect metric changes to the other recorded differences.
    - State a conclusion that fits the available evidence.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=uu01blkTRRg" data-apizr-video="uu01blkTRRg" data-apizr-title="Compare experiment Runs: data, models and metrics" aria-label="Play: Compare experiment Runs: data, models and metrics">
    <img src="../../assets/videos/tutorial-experiment-comparison.png" width="1280" height="720" loading="lazy" alt="Academy Part VIII: compare actual data identities and metric deltas" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 7:15 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Keep comparison direction explicit

Use the two retained fraud Runs from the [data-science walkthrough](../getting-started/data-science.md). If you have not produced them yet, follow its two-run steps before continuing. Copy their actual IDs from history:

```sh
apizr experiment list
apizr experiment diff RUN_A RUN_B
apizr experiment diff RUN_B RUN_A
```

Replace the placeholders with those IDs. A numeric delta in A → B is **B minus A**. The reverse comparison changes its sign. Added and removed evidence also reverse their roles.

## 2. Separate a difference from its explanation

Suppose an exercise has scores `0.91` and `0.92`. Its forward delta is `+0.01`, not “one percent better at the task”. These numbers illustrate arithmetic; they are not the measured fraud results. For the actual exercise, read the retained metric values in your own two Runs.

A changed input fingerprint or parameter can help you investigate. It does not, by itself, prove which change caused a result. Unknown evidence stays unknown rather than becoming evidence of equality.

## Practice

1. Write down one actual metric in each Run and calculate the forward delta before opening the comparison.
2. Predict the reverse delta and check it.
3. List the recorded differences in data, code, parameters and outputs. Explain why the synthetic cohort comparison does not prove that the model generalizes better to a real fraud population.

??? success "Check your reasoning"

    Your arithmetic should match `value_B - value_A`; reversing the Run order negates that delta when both values are known and comparable.

    The cohorts’ label-rule change affects what was measured. A defensible conclusion describes the observed score and identity changes under this setup, then states what is missing for a broader scientific claim. You would need a suitable evaluation design and evidence about the population and target task, rather than just a positive diff.

[Back to the Academy](index.md) · [Continue to the next lesson](model-serving.md)
