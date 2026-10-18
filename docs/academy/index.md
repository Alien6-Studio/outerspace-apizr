---
title: Apizr Academy
hide:
  - toc
description: Learn to build useful Python interfaces, interpret experiment evidence and review real Runs through twelve video lessons with practical exercises and corrections.
---

# Apizr Academy

<div class="apizr-academy-intro" markdown="1">
<p class="apizr-academy-kicker">Learn it. Try it. Explain the result.</p>

## From useful Python code to results you can explain

A teammate gives you a Python function and a training notebook. What can you safely describe? Which function should become callable? What did an experiment actually record, and what remains unknown?

Work through those questions in **12 complete lessons**. Each has an integrated video, a written explanation, a concrete exercise and a correction you can open after trying it. You need basic Python; no prior Apizr or MCP knowledge is assumed.

[Start with lesson 1](install.md){ .md-button .md-button--primary }
[Choose your learning path](#choose-your-learning-path){ .md-button }

<div class="apizr-academy-facts"><span><strong>12</strong> video lessons</span><span><strong>74 min</strong> of course videos</span><span><strong>3</strong> practical learning paths</span></div>
</div>

!!! info "Choose the environment before you begin"
    The exercises target **Apizr 0.4.6 development**, which is not a published package release. [Lesson 1](install.md) explains how to choose the documented development installation or the stable 0.4.5 alternative. Earlier videos retain their originally demonstrated version. The practice-time estimates include watching and trying the exercise; take longer whenever you need it.

## Choose your learning path

<div class="apizr-academy-paths" markdown="1">

<article markdown="1">

### [01 · Build a service](#build-a-service)

For Python developers making a function callable by an application or an AI client. Begin with installation and inspection, make real REST and MCP calls, then understand the container handoff.

**Lessons 1–5 · 29 min of video · hands-on work at your pace**

</article>

<article markdown="1">

### [02 · Understand experiments](#understand-experiments)

For developers and data scientists reading a notebook or selecting a prediction model. Distinguish source evidence, observed Runs, recorded differences and the precise context selected for serving.

**Lessons 6–9 · 27 min of video · requires the lesson 1 environment**

</article>

<article markdown="1">

### [03 · Track and review](#track-and-review)

For people who already work in Python, Jupyter or VS Code. Choose meaningful capture boundaries, read actual execution history and review measured results in the editor.

**Lessons 10–12 · 19 min of video · basic Run concepts from lessons 6–8 help**

</article>

</div>

## Build a service

Start with the shop’s price and stock calculations. Your result is a real local call, plus an explanation of what generation, execution and publication each establish.

<div class="apizr-academy-courses" markdown="1">
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="install/"><img src="../assets/videos/tutorial-install.jpg" alt="Lesson 1: Install Apizr in the right environment" loading="lazy" width="1280" height="720" /></a>

<span id="01-install"></span>
### 01 · [Install Apizr in the right environment](install.md)

Choose an installation you can explain and verify.

<p class="apizr-academy-course__time">Video 6:39 · Plan about 20 min</p>

[Open the lesson](install.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="inspect/"><img src="../assets/videos/tutorial-inspect.jpg" alt="Lesson 2: Read a Python contract before running code" loading="lazy" width="1280" height="720" /></a>

<span id="02-inspect"></span>
### 02 · [Read a Python contract before running code](inspect.md)

Separate a callable description, readiness and permission.

<p class="apizr-academy-course__time">Video 4:11 · Plan about 20 min</p>

[Open the lesson](inspect.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="rest/"><img src="../assets/videos/tutorial-rest.jpg" alt="Lesson 3: Turn a selected function into a REST call" loading="lazy" width="1280" height="720" /></a>

<span id="03-rest"></span>
### 03 · [Turn a selected function into a REST call](rest.md)

Connect Python arguments, an HTTP request and an observed response.

<p class="apizr-academy-course__time">Video 4:14 · Plan about 25 min</p>

[Open the lesson](rest.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="mcp/"><img src="../assets/videos/tutorial-mcp.jpg" alt="Lesson 4: Expose the same calculation as an MCP tool" loading="lazy" width="1280" height="720" /></a>

<span id="04-mcp"></span>
### 04 · [Expose the same calculation as an MCP tool](mcp.md)

Discover and call a tool before introducing an AI client.

<p class="apizr-academy-course__time">Video 5:09 · Plan about 25 min</p>

[Open the lesson](mcp.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="oci/"><img src="../assets/videos/tutorial-oci.jpg" alt="Lesson 5: Package a service for another machine" loading="lazy" width="1280" height="720" /></a>

<span id="05-oci"></span>
### 05 · [Package a service for another machine](oci.md)

Distinguish a generated bundle, a built image and a published image.

<p class="apizr-academy-course__time">Video 8:21 · Plan about 30 min</p>

[Open the lesson](oci.md)

</article>
</div>

<span id="experiment-path-recordings-coming-later"></span>
<span id="experiment-path-recordings-in-preparation"></span>

## Understand experiments

Follow the synthetic fraud case through inspection, retained Runs, comparison and a selected prediction. Each lesson also offers a smaller exercise to make the evidence easier to reason about.

<div class="apizr-academy-courses" markdown="1">
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="experiment-inspection/"><img src="../assets/videos/tutorial-experiment-inspection.png" alt="Lesson 6: Inspect a notebook without inventing results" loading="lazy" width="1280" height="720" /></a>

<span id="06-inspect-experiment-evidence"></span>
### 06 · [Inspect a notebook without inventing results](experiment-inspection.md)

Tell source evidence from values observed during execution.

<p class="apizr-academy-course__time">Video 5:54 · Plan about 20 min</p>

[Open the lesson](experiment-inspection.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="runs/"><img src="../assets/videos/tutorial-experiment-history.png" alt="Lesson 7: Run trusted code and read its retained evidence" loading="lazy" width="1280" height="720" /></a>

<span id="07-run-an-experiment-and-read-its-history"></span>
### 07 · [Run trusted code and read its retained evidence](runs.md)

Connect the intended Plan, the observed Run and the files you retain.

<p class="apizr-academy-course__time">Video 6:15 · Plan about 25 min</p>

[Open the lesson](runs.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="comparison/"><img src="../assets/videos/tutorial-experiment-comparison.png" alt="Lesson 8: Compare Runs and interpret a metric delta" loading="lazy" width="1280" height="720" /></a>

<span id="08-compare-experiment-runs"></span>
### 08 · [Compare Runs and interpret a metric delta](comparison.md)

Describe observed differences without claiming they caused an improvement.

<p class="apizr-academy-course__time">Video 7:15 · Plan about 25 min</p>

[Open the lesson](comparison.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="model-serving/"><img src="../assets/videos/tutorial-experiment-exposure.png" alt="Lesson 9: Bind a reviewed model to a callable prediction" loading="lazy" width="1280" height="720" /></a>

<span id="09-expose-a-selected-prediction"></span>
### 09 · [Bind a reviewed model to a callable prediction](model-serving.md)

Choose exact evidence, model bytes and an interface.

<p class="apizr-academy-course__time">Video 6:50 · Plan about 30 min</p>

[Open the lesson](model-serving.md)

</article>
</div>

## Track and review

Move from explicit Python capture to a live Jupyter kernel, then review real Wine classification Runs in VS Code. Keep the observation separate from the scientific conclusion.

<div class="apizr-academy-courses" markdown="1">
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="python-tracking/"><img src="../assets/videos/tutorial-sdk.png" alt="Lesson 10: Choose the unit you capture in Python" loading="lazy" width="1280" height="720" /></a>

<span id="10-track-python-calls"></span>
### 10 · [Choose the unit you capture in Python](python-tracking.md)

Record useful observations while preserving ordinary function behaviour.

<p class="apizr-academy-course__time">Video 6:30 · Plan about 25 min</p>

[Open the lesson](python-tracking.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="jupyter/"><img src="../assets/videos/tutorial-jupyter.png" alt="Lesson 11: Read a notebook’s actual execution history" loading="lazy" width="1280" height="720" /></a>

<span id="11-capture-real-jupyter-cells"></span>
### 11 · [Read a notebook’s actual execution history](jupyter.md)

Distinguish saved cells, live state and recorded cell executions.

<p class="apizr-academy-course__time">Video 5:56 · Plan about 25 min</p>

[Open the lesson](jupyter.md)

</article>
<article class="apizr-academy-course" markdown="1">
<a class="apizr-academy-course__cover" href="vscode/"><img src="../assets/videos/tutorial-vscode.png" alt="Lesson 12: Review real experiment Runs in VS Code" loading="lazy" width="1280" height="720" /></a>

<span id="12-review-real-experiment-runs-in-vs-code"></span>
### 12 · [Review real experiment Runs in VS Code](vscode.md)

Read recorded source, compare measured Wine Runs and recognize stale evidence.

<p class="apizr-academy-course__time">Video 6:22 · Plan about 30 min</p>

[Open the lesson](vscode.md)

</article>
</div>

## See the whole journey

<span id="00-see-the-result"></span>
Before the course, watch this 2:34 demonstration of a route calculation used through REST and MCP. It shows the end result; the lessons above explain the decisions and let you practise them.

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=u8e0fi2m80M" data-apizr-video="u8e0fi2m80M" data-apizr-title="Turn existing Python expertise into APIs and AI tools" aria-label="Play: Turn existing Python expertise into APIs and AI tools">
    <img src="../assets/videos/paris-route.jpg" width="1920" height="1080" loading="lazy" alt="Apizr route-planning demonstration" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the demo</span>
  </a>
</div>

[Open the Academy playlist on YouTube](https://www.youtube.com/playlist?list=PLPxU4WUOuPeQ).

## Keep the concepts close

Use these short references whenever a lesson raises a question: [Capability](capabilities.md), [Readiness](readiness.md), [Exposure](exposure.md), [Execution](execution.md) and [Interfaces](interfaces.md). The [written walkthrough](../getting-started/quickstart.md) and [notebook-to-service guide](../getting-started/data-science.md) provide the complete commands.

Videos play inside the lesson after you select Play. Their covers are local; YouTube loads only at that point through its privacy-enhanced player. You can complete the written exercises without loading a video.

<span id="start-here-from-python-to-a-callable-service"></span>

<span id="understand-the-decisions"></span>

<span id="experiment-path-from-evidence-to-serving"></span>
