---
title: Capture real Jupyter cells and the hidden calibration change
description: Read four real captures, repeat first-variant and explain the unlogged offset.
lesson: 11
recording: 11-jupyter
---

<p class="apizr-academy-kicker">Track and review · Lesson 11</p>

# Capture real Jupyter cells and the hidden calibration change

The video drives a real ipykernel through a terminal. It uses the **same fraud holdout** as lesson 10, then changes an unlogged calibration offset before repeating a captured cell. It is not a recording of a Jupyter graphical frontend.

!!! abstract "By the end of this lesson"
    - Distinguish notebook file identity, kernel cell identity and Run identity.
    - Predict the four retained captures, including a repeated cell.
    - Explain the actual effect of the unlogged calibration_offset.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=VqTmKCU-Auo" data-apizr-video="VqTmKCU-Auo" data-apizr-title="Capture real Jupyter cells" aria-label="Play: Track real Jupyter cell executions and hidden kernel state">
    <img src="../../assets/videos/tutorial-jupyter.png" width="1280" height="720" loading="lazy" alt="Academy Part XI: inspect real Jupyter cell executions and retained Runs" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Use the recorded notebook and holdout

Prepare `evaluation.csv` as in [lesson 10](python-tracking.md), using the `fraud-detection/` folder in the [recorded materials](../downloads/academy-recorded-examples.zip). That folder includes the actual `fraud-thresholds.ipynb`, not a substitute demonstration notebook.

For manual practice, open it with the scientific environment's Jupyter kernel, execute its code cells in order, then repeat `first-variant` after `calibration-change`. Defining the decorated function is not an evaluation call.

**Exact terminal replay:** the recording uses the product checkout's `scripts.qualification.experiments.academy_kernel` driver. With its source root on `PYTHONPATH`, run the selected scientific interpreter using:

```sh
python -m scripts.qualification.experiments.academy_kernel --notebook fraud-thresholds.ipynb --workspace "$APIZR_ACADEMY_KERNEL_WORKSPACE" --input evaluation.csv --pause 3
```

Set `APIZR_ACADEMY_KERNEL_WORKSPACE` to a fresh directory outside the checkout. The driver sends the actual cells to ipykernel and then repeats `first-variant`; it checks the four resulting captures. The [recording procedure](production.md) describes the checkout/interpreter selection for this terminal driver.

## 2. Read the four captures

The retained recording shows one session, two threshold calls, then the first call again:

| Captured cell | Kernel count in the recording | Threshold | Flagged rows |
| --- | ---: | ---: | ---: |
| `session` | 2 | 0.5 | 35 |
| `first-variant` | 4 | 0.35 | 60 |
| `second-variant` | 5 | 0.65 | 21 |
| `first-variant`, repeated | 7 | 0.35 | 103 |

Use `apizr experiment list` and `show` on that workspace's history. With the terminal driver, select `--store "$APIZR_ACADEMY_KERNEL_WORKSPACE/.apizr/experiments/v1"`. Your own frontend may provide different cell metadata or execution counts; read what was actually captured.

## 3. Explain the calibration variant

Before the repeated call, the notebook changes **`calibration_offset` from 0.0 to 0.2** in live memory without logging it. The threshold and selected CSV identity stay the same. Yet the repeated `first-variant` flags **103 rather than 60** rows; recorded recall changes from **0.6875 to approximately 0.9792**.

The saved input file, cell ID and logged threshold do not identify all live kernel state. A new execution count tells you order, not the values of every in-memory object.

## Practice

Use the filmed question: must the same cell ID and threshold produce the same metric after an unlogged in-memory input changes? Can the execution count tell you which values were used? Propose the missing observation.

??? success "Check your reasoning"

    The same cell can read different live state. A new count and Run preserve a distinct execution, not a complete memory snapshot. In this case, explicitly log `calibration_offset` as a parameter and preserve the relevant source. Keep that proposed correction separate from the recording, which deliberately leaves the offset unlogged to demonstrate the limitation.

<span id="1-use-the-environment-of-the-actual-kernel"></span>
<span id="2-observe-execution-rather-than-assuming-file-order"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](vscode.md)
