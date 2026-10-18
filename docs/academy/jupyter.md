---
title: Read a notebook’s actual execution history
description: Distinguish saved cells, live state and recorded cell executions.
lesson: 11
---

<p class="apizr-academy-kicker">Track and review · Lesson 11 · Plan about 25 min</p>

# Read a notebook’s actual execution history

A notebook looks ordered from top to bottom, but its kernel remembers the order in which cells actually ran. A changed threshold can remain in memory even when the visible saved notebook suggests a different value.

You will repeat a real captured cell and examine the new Run, its available cell identity and execution count. Treat the notebook file and the live kernel as related sources of evidence with different limits.

!!! abstract "By the end of this lesson"
    - Distinguish a saved notebook from its current kernel state.
    - Recognize a repeated captured cell as a new execution.
    - Explain what selected file and parameter evidence leaves unknown.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=VqTmKCU-Auo" data-apizr-video="VqTmKCU-Auo" data-apizr-title="Track real Jupyter cell executions and hidden kernel state" aria-label="Play: Track real Jupyter cell executions and hidden kernel state">
    <img src="../../assets/videos/tutorial-jupyter.png" width="1280" height="720" loading="lazy" alt="Academy Part XI: inspect real Jupyter cell executions and retained Runs" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 5:56 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Use the environment of the actual kernel

Install the development SDK in the interpreter selected by Jupyter, following [lesson 1](install.md). Open the [runnable capture notebook](../getting-started/tracking.md#3-use-the-same-calls-in-jupyter) and run its cells in order in a fresh exercise directory.

The same SDK calls work in the live kernel. The recording shows real ipykernel execution through a terminal; it is not a demonstration of the Jupyter graphical interface.

## 2. Observe execution, rather than assuming file order

List the history from that working directory and interpreter:

```sh
apizr experiment list
apizr experiment show RUN_ID
```

Replace `RUN_ID` with an actual retained identifier. Read the capture context, available cell identity, execution count, selected parameters and observations. A frontend may not provide every piece of cell metadata. Missing evidence should remain explicit.

A saved file’s hash identifies its bytes. It does not identify all current in-memory objects. Equally, an execution count helps interpret an observed cell execution; it does not prove scientific reproducibility of the entire notebook.

## Practice

1. Run a captured cell, record its Run ID and available execution count, then run that same cell again.
2. Check that a new Run exists and explain the observed counts.
3. Change an in-memory setting in another cell. Before executing the captured cell again, predict which selected parameter or metric should reflect that change. Explain what you could still not reconstruct from the saved notebook alone.

??? success "Check your reasoning"

    Repeating a captured execution creates a new Run. Its observed execution context can differ even when the visible source text is the same. Selected runtime parameters and metrics help describe the execution that actually occurred.

    The saved notebook alone may omit the live sequence and state that led there. A Run also does not snapshot every in-memory object. Keep selected file identities, explicit parameters and those unknowns separate when interpreting or sharing results.

[Back to the Academy](index.md) · [Continue to the next lesson](vscode.md)
