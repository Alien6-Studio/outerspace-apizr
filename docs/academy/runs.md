---
title: Run trusted code and read its retained evidence
description: Connect the intended Plan, the observed Run and the files you retain.
lesson: 7
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 07 · Plan about 25 min</p>

# Run trusted code and read its retained evidence

You have reviewed the source and decided to execute it. Later, someone asks which computation produced a model file. A filename is insufficient; you need the intended execution, its observed outcome and the identity of selected files.

You will run a tiny standard-library workload, read its retained record, and then deliberately separate an artifact’s recorded identity from the continued availability of its bytes.

!!! abstract "By the end of this lesson"
    - Distinguish a Plan from runtime observations in a Run.
    - Find a retained Run by its identifier and inspect its outcome.
    - Explain why a recorded model fingerprint is not an artifact backup.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=XHszreGQhMY" data-apizr-video="XHszreGQhMY" data-apizr-title="Run an experiment and read its history" aria-label="Play: Run an experiment and read its history">
    <img src="../../assets/videos/tutorial-experiment-history.png" width="1280" height="720" loading="lazy" alt="Academy Part VII: connect an actual experiment Run to retained evidence" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 6:15 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Execute a complete, trusted workload

`experiment run` executes trusted code with the host access of its environment. A fresh process does not make it a filesystem or network sandbox. Use a fresh directory for this example:

```sh
cat > local_run.py <<'PYTHON'
from pathlib import Path
mean = sum([2, 4, 6]) / 3
Path("model.json").write_text('{"mean": 4.0}\n')
PYTHON
RUN=$(apizr experiment run local_run.py --metric mean=mean --output model=model.json --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run_digest"])')
apizr experiment list
apizr experiment show "$RUN"
```

The metric selector asks for the final `mean` binding. The output selector asks for `model.json` after success. Their names make the required observations explicit.

<div class="apizr-academy-flow" role="group" aria-label="Plan and observation"><span>Plan: source and controls</span><span>Execute trusted code</span><span>Run: status and observations</span></div>

## 2. Read what was retained

The Plan records intended identities and execution controls. The Run adds observed status and evidence. The local history stores the record, including selected output fingerprints; it does not store a copy of every output file.

A failed Run is also an outcome worth reading. Do not infer success from the mere presence of a Run ID. See the [history guide](../getting-started/user-guide/experiment-runs.md) for status and failure codes.

## Practice

1. Locate the `mean` observation and explain why its value is `4.0`.
2. Keep the Run ID, then replace `model.json` with different bytes. Read the earlier Run again.
3. Decide what you would need to retain to serve the originally selected model later.

??? success "Check your reasoning"

    The earlier record still identifies the original selected output. It has not become a record of the replacement file, and reading it cannot restore the original bytes.

    Retain the actual model artifact under your own storage policy as well as its record. To serve it later, you need those matching bytes, the reviewed source and the required runtime dependencies. An artifact’s hash answers an identity question, not a storage or availability question.

[Back to the Academy](index.md) · [Continue to the next lesson](comparison.md)
