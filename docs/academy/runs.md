---
title: Run the fraud notebook and read retained history
description: Connect Plan, actual metrics and model identity, then test a corrupted store.
lesson: 7
recording: 07-history
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 07</p>

# Run the fraud notebook and read retained history

The video executes the reviewed fraud notebook and asks which data and settings produced its saved model. It then replaces the current CSV and deliberately damages a disposable copy of the evidence store.

!!! abstract "By the end of this lesson"
    - Separate the intended Plan from observed Run evidence.
    - Read a retained Run by its exact identity.
    - Explain artifact retention and the recorded integrity refusal.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=XHszreGQhMY" data-apizr-video="XHszreGQhMY" data-apizr-title="Run an experiment and read its history" aria-label="Play: Run an experiment and read its history">
    <img src="../../assets/videos/tutorial-experiment-history.png" width="1280" height="720" loading="lazy" alt="Academy Part VII: connect an actual experiment Run to retained evidence" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Execute the reviewed workload

Use a fresh `fraud-detection/` copy from the [recorded source materials](../downloads/academy-recorded-examples.zip), with cohort A active. Install the notebook's scientific requirements in the selected [development environment](../getting-started/data-science.md). The process executes trusted code with host access; Apizr does not install pandas or scikit-learn for it.

```sh
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-a.json
python lab.py run run-a.json
apizr experiment list
RUN_A=$(python -c 'import json; print(json.load(open("run-a.json"))["run_digest"])')
apizr experiment show "$RUN_A" --format json > retained-a.json
python lab.py run retained-a.json
```

The Plan identifies intended source, inputs and controls. The Run contains the observed outcome, metrics and selected output identity. Read parameter origins rather than assuming every source candidate or declared seed became a runtime observation. Success means this execution completed; precision, recall and AUC still require interpretation.

## 2. Replace the CSV without rewriting Run A

```sh
cp data/transactions-b.csv data/transactions.csv
python lab.py retain
apizr experiment show "$RUN_A" --format json > retained-a-after.json
```

The file at the same path now has different bytes. The retained record remains bound to the input of A. Its fingerprints identify data and the selected model; they do not archive either file's contents.

## 3. Test the recorded integrity boundary

Work on a copied store, keeping the original history untouched:

```sh
cp -R .apizr/experiments/v1 damaged-store
printf ' ' >> "damaged-store/runs/$RUN_A.json"
apizr experiment show "$RUN_A" --store damaged-store --format json > refused.json 2> refused.log
```

The final command is expected to be refused with exit 2: syntactically readable JSON can still violate canonical bytes and the stored identity. This demonstrates local evidence integrity, not a signature or independent authorization.

## Practice

Answer the video's artifact-retention question. If tomorrow's training overwrites `model.joblib`, can `show` restore A's model? What must another engineer preserve to serve exactly that model later?

??? success "Check your reasoning"

    The record cannot recreate overwritten model bytes. Retain the actual selected model and needed input bytes through your artifact-retention process, alongside the Run. Their hashes let you check identity; the copied-store refusal shows why altering a retained record is not a valid way to change its evidence.

<span id="1-execute-a-complete-trusted-workload"></span>
<span id="2-read-what-was-retained"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](comparison.md)
