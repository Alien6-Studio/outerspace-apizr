---
title: Bind a reviewed model to a callable prediction
description: Choose exact evidence, model bytes and an interface.
lesson: 9
---

<p class="apizr-academy-kicker">Understand experiments · Lesson 09 · Plan about 30 min</p>

# Bind a reviewed model to a callable prediction

You have chosen a successful Run. The model file at the old path has since been replaced. Should serving silently use the newer file because its name is convenient?

This lesson treats the selection as a precise handoff: a reviewed Run, an eligible prediction function, matching selected artifacts and explicit dependencies.

!!! abstract "By the end of this lesson"
    - Select one Run and prediction capability rather than exposing training.
    - Explain how source and artifact identities constrain the binding.
    - Distinguish a generated serving bundle from a deployed prediction service.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=s68H9yhNWgk" data-apizr-video="s68H9yhNWgk" data-apizr-title="Bind a retained model to REST and MCP" aria-label="Play: Bind a retained model to REST and MCP">
    <img src="../../assets/videos/tutorial-experiment-exposure.png" width="1280" height="720" loading="lazy" alt="Academy Part IX: bind a selected model to local REST and MCP bundles" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 6:50 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Make the handoff concrete

Follow the [small training-to-serving example](../getting-started/user-guide/experiment-exposure.md#small-training-to-serving-example). It creates a coefficient file and a separate debug output. The prediction function reads the coefficient; training is behind the ordinary Python main guard.

The exercise selects `python:serving:predict` and the artifact named `model`. Selecting one recorded output does not select every file the workload wrote. For the fraud example in the video, also select the required scientific distributions explicitly.

<div class="apizr-academy-flow" role="group" aria-label="Selected serving context"><span>Successful Run</span><span>Matching model and source</span><span>Selected REST or MCP bundle</span></div>

## 2. Read the resulting binding

Use the guide’s `experiment expose` commands for REST and MCP. Read their saved binding documents: the chosen Run, capability, artifact identities and generated bundle should be identifiable. Exposure validates evidence and source; it does not rerun training to manufacture a missing model.

The source still needs to be eligible under Readiness and accessible under the selected operator policy. A successful training Run does not exempt an unsupported prediction contract from these checks.

## Practice

1. Generate both bindings using the guide’s original coefficient file. Identify the selected model and the unselected debug output.
2. Change the model bytes and attempt a new binding into a fresh output directory.
3. Explain why substituting this model under the earlier record would weaken the handoff, even if its prediction still looks plausible.

??? success "Check your reasoning"

    The changed bytes do not have the selected artifact identity, so the handoff must be refused rather than silently rebound. The original matching model must be retained if you intend to serve that Run’s selected context.

    A bundle describes and packages a selected interface context. Running its actual transports, operating the service and deploying it remain additional work. Its existence does not establish production performance, access control or availability.

[Back to the Academy](index.md) · [Continue to the next lesson](python-tracking.md)
