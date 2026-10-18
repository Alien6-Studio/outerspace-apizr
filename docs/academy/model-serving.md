---
title: Expose the retained fraud prediction model
description: Select the Run, fraud_detection.predict, model bytes and scientific dependencies.
lesson: 9
recording: 09-exposure
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 09</p>

# Expose the retained fraud prediction model

The application team wants a fraud prediction, not another training run. The video separates the notebook's training path from its typed prediction function and binds the exact retained model to REST and MCP.

!!! abstract "By the end of this lesson"
    - Identify the prediction's model, feature helper and serving dependencies.
    - Make the four recorded serving choices explicit.
    - Observe a stale model refusal and restore the selected bytes.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=s68H9yhNWgk" data-apizr-video="s68H9yhNWgk" data-apizr-title="Expose a selected prediction" aria-label="Play: Bind a retained model to REST and MCP">
    <img src="../../assets/videos/tutorial-experiment-exposure.png" width="1280" height="720" loading="lazy" alt="Academy Part IX: bind a selected model to local REST and MCP bundles" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Read the actual serving boundary

Use a fresh fraud lab from the [recorded materials](../downloads/academy-recorded-examples.zip), its scientific environment and a wheelhouse prepared for that environment as described in the [data-science guide](../getting-started/data-science.md). Set `SCIENCE_WHEELHOUSE` to that actual wheelhouse path.

```sh
python lab.py source predict
python lab.py source settings
cp data/transactions-b.csv data/transactions.csv
apizr experiment run fraud_detection.ipynb --output model=artifacts/model.joblib --format json > run-b.json
python lab.py run run-b.json
```

`fraud_detection.predict` accepts a typed transaction with amount, velocity, foreign flag and account age. It loads the selected joblib model and uses `features.py` to preserve feature order. Training stays behind the Python main guard. Joblib and scikit-learn are serving dependencies here; pandas belongs to training.

## 2. Make the four choices and inspect both bindings

Choose the retained Run, `python:fraud_detection:predict`, the logical artifact `model`, and scientific dependency evidence. Create the copied project's analysis grant, then expose the two interfaces:

```sh
python -c 'import json; from pathlib import Path; Path("operator.json").write_text(json.dumps({"schema":"apizr.operator-policy/v1","grants":[{"adapter":"repository","operation":"analyze","target":{"kind":"local","root":str(Path.cwd())},"permissions":["source.analyze"]}]}))'
RUN_B=$(python -c 'import json; print(json.load(open("run-b.json"))["run_digest"])')
for interface in rest mcp; do
  apizr experiment expose "$RUN_B" --root . --operator-policy operator.json --capability python:fraud_detection:predict --interface "$interface" --artifact model --dependency scikit-learn --dependency joblib --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional --output-dir "bundles/$interface" > "$interface-exposure.json"
done
python lab.py binding
```

`--allow-conditional` acknowledges opaque external dependency code; it is not a certificate of safe execution. The recording inspects generated local bundles. It does not start a server, demonstrate runtime isolation or deploy a prediction service. The training marker is absent from both serving bundles.

## 3. Replay the stale-model variant

```sh
cp artifacts/model.joblib artifacts/original-model.joblib
printf 'altered' >> artifacts/model.joblib
apizr experiment expose "$RUN_B" --root . --operator-policy operator.json --capability python:fraud_detection:predict --interface rest --artifact model --dependency scikit-learn --dependency joblib --dependency-wheelhouse "$SCIENCE_WHEELHOUSE" --allow-conditional --output-dir bundles/stale > refused.json 2> refused.log
```

The recorded refusal is **`run_artifact_changed`**, exit 2. Restore the saved model with `python lab.py restore-model`; the helper verifies the selected digest again.

## Practice

Answer the filmed question: a newer training run replaces `model.joblib`. Should the original Run silently use it? Which identity should you check, and why is the training marker not a serving dependency?

??? success "Check your reasoning"

    A path is not the selected model identity. Preserve and verify the matching bytes instead of substituting a newer artifact. Only the selected serving artifacts belong in the binding. A training-side marker's presence in the experiment folder does not make prediction depend on it.

<span id="1-make-the-handoff-concrete"></span>
<span id="2-read-the-resulting-binding"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](python-tracking.md)
