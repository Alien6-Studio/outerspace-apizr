---
title: Inspect the fraud notebook before training
description: Read static evidence, change the CSV and distinguish notebook bytes from scientific signals.
lesson: 6
recording: 06-inspection
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 06</p>

# Inspect the fraud notebook before training

The recording reviews the committed **synthetic fraud notebook**: a random forest, a held-out split, three metrics and a saved prediction model. It asks what can be established before training, then tests two different kinds of file change.

!!! abstract "By the end of this lesson"
    - Explain why a recognized AUC call has no observed score during inspection.
    - Distinguish a CSV path from its content identity.
    - Separate raw notebook bytes from the identity of scientific signals.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=9P5F42RYCRs" data-apizr-video="9P5F42RYCRs" data-apizr-title="Inspect experiment evidence" aria-label="Play: Inspect a machine learning notebook without running it">
    <img src="../../assets/videos/tutorial-experiment-inspection.png" width="1280" height="720" loading="lazy" alt="Academy Part VI: inspect experiment evidence before training" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Prepare the same case

Download the [recorded VI–XII source materials](../downloads/academy-recorded-examples.zip). For each fraud lesson, start with a fresh copy of its `fraud-detection/` directory and restore `data/transactions-a.csv` as `data/transactions.csv`. The archive includes the actual notebook, both synthetic cohorts and `lab.py` from the video.

Use the [0.4.6 development environment](../development/0.4.md#install-a-development-wheel). Inspection reads notebook source; it does not need to import the scientific workload. Later execution lessons require that workload's pinned `requirements.txt` too.

```sh
cp data/transactions-a.csv data/transactions.csv
python lab.py source settings
apizr experiment inspect fraud_detection.ipynb --format json > inspection-a.json
python lab.py inspection inspection-a.json
```

Read the visible settings: 24 trees, maximum depth 5, a quarter reserved for evaluation and seed 42. These are source statements, not proof that training ran. In the recording, execution is `not_executed`, parameters are captured as candidates, metrics remain partial, and no trained model exists. The dynamic `joblib.load` reference leaves data evidence partial even alongside an identified CSV.

## 2. Same filename, different cohort

```sh
cp data/transactions-b.csv data/transactions.csv
apizr experiment inspect fraud_detection.ipynb --format json > inspection-b.json
python lab.py inspect-change
```

The CSV's bytes change while its path, notebook and declared hyperparameters remain the same. Neither inspection produces an AUC value or a model.

## 3. Replay the recorded presentation variant

```sh
python lab.py presentation
apizr experiment inspect fraud_detection.ipynb --format json > presentation.json
python lab.py signal-check
```

The helper changes stored execution counts and presentation metadata without executing a cell or editing its code. The retained result is **different raw notebook bytes, equal scientific-signal digest**, and execution still `not_executed`. These identities answer different questions.

## Practice

Use the video's question: a colleague sees a seed, captured parameters and an AUC calculation, then claims a reproducible model score. Identify two unsupported claims and choose the next operation and environment.

??? success "Check your reasoning"

    No AUC value was observed because the notebook was not executed. A declared seed does not establish a reproduced outcome across environments. If you trust the notebook, explicitly run it in the environment containing its scientific dependencies. Preserve the inspection's evidence and unknowns instead of treating its populated sections as a completed experiment.

<span id="1-inspect-an-intentionally-incomplete-example"></span>
<span id="2-read-the-report-as-separate-questions"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](runs.md)
