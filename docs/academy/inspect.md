---
title: Read a Python contract before running code
description: Separate a callable description, readiness and permission.
lesson: 2
---

<p class="apizr-academy-kicker">Build a service · Lesson 02 · Plan about 20 min</p>

# Read a Python contract before running code

You want to expose a small price calculation. Before starting a server, you need to know what the function accepts and whether Apizr can describe its interface. You do not need to execute the application to answer that first question.

This lesson follows the chain from a Python declaration to a capability and its readiness reasons. A positive readiness decision is one input to your next choice; it does not make that choice for you.

!!! abstract "By the end of this lesson"
    - Identify a capability’s name, inputs and return description.
    - Read a readiness reason and decide what to change.
    - Explain why inspection, selection and execution are separate actions.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=Ypgp8fCof0E" data-apizr-video="Ypgp8fCof0E" data-apizr-title="Inspect a project and understand readiness" aria-label="Play: Inspect a project and understand readiness">
    <img src="../../assets/videos/tutorial-inspect.jpg" width="480" height="360" loading="lazy" alt="Academy Part II: inspect a project" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 4:11 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Start with a small contract

Save this as `pricing.py` in a fresh exercise directory:

```python
def quote(unit_price: float, quantity: int) -> float:
    return unit_price * quantity
```

Inspect the declaration:

```sh
apizr inspect pricing.py
apizr inspect pricing.py --format json
```

Read the capability name, parameter types, return annotation and readiness reasons. Inspection reads source; it does not call `quote`. The return annotation describes the expected shape, rather than proving that the implementation returns a correct price.

<div class="apizr-academy-flow" role="group" aria-label="Three separate decisions"><span>Describe the function</span><span>Read eligibility reasons</span><span>Select an interface</span></div>

## 2. Follow the reason, rather than a colour

A `ready` function has enough static evidence for the supported ordinary value interface. A conditional binding needs investigation; an unsupported shape needs a suitable adapter or a different callable. For example, a generator produces a stream rather than the single ordinary value expected here.

A helper needed to implement `quote` can be included in a bundle without receiving its own public operation. This distinction matters when your project grows beyond a single file.

## Practice

1. Inspect `pricing.py` and locate the declaration of `quantity`.
2. Change the function’s body to return `"not a price"`, keeping the `-> float` annotation. Inspect it again. Has the annotation become a runtime test?
3. Restore the calculation. In a separate file, write a generator with `yield` and inspect its reasons. Explain why an ordinary REST operation should not silently pretend that this is the same contract.

??? success "Check your reasoning"

    Inspection retains the declared contract and its limitations. An annotation is not evidence that the implementation obeys it on every path. A generation eligibility decision also does not authorize execution or prove scientific correctness.

    The generator requires streaming semantics that the ordinary value adapter does not define. Read the specific reason instead of removing the refusal. Keep the ordinary calculation for the next exercises.

[Back to the Academy](index.md) · [Continue to the next lesson](rest.md)
