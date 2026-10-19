---
title: "Read your code. Understand the contract."
description: Separate setup checks, repository inventory and the unsupported Requests.get contract.
lesson: 2
recording: 02-understand
---

<p class="apizr-academy-kicker">Build interfaces · Lesson 02</p>

<span id="read-requests-with-doctor-scan-and-inspect"></span>

# Read your code. Understand the contract.

The video uses **Requests**, not a newly written pricing function. It asks three separate questions: is the local setup prepared, what source exists, and which contracts can this interface generator support?

!!! abstract "By the end of this lesson"
    - Use doctor, scan and inspect for their distinct purposes.
    - Read a readiness state with its concrete reason.
    - Explain why selecting Requests.get does not remove its variadic signature.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=Ypgp8fCof0E" data-apizr-video="Ypgp8fCof0E" data-apizr-title="Read your code. Understand the contract." aria-label="Play: Read your code. Understand the contract.">
    <img src="../../assets/videos/academy-02-youtube.jpg" width="1280" height="720" loading="lazy" alt="Lesson 02: Read your code. Understand the contract." />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Pin Requests and prepare its source root

The recorded checkout is `psf/requests` at `v2.32.5`, analysed with Apizr 0.4.3. Follow it in a fresh directory:

```sh
git clone --depth 1 --branch v2.32.5 https://github.com/psf/requests.git
cd requests
apizr init . --source-root src
cat apizr.toml
apizr doctor --project apizr.toml --operator-policy .apizr/operator.json
```

`init` writes configuration and a local analysis grant. It does not select public capabilities. Doctor's empty-selection warning is expected at this point. It checks preparation without scanning or repairing the project automatically.

## 2. Inventory, then explain one refusal

```sh
apizr scan . --source-root src --operator-policy .apizr/operator.json > scan.txt
apizr inspect src/requests/api.py > inspection.txt
```

These recorded analyses return diagnostics and may exit nonzero; read their saved reports. The recording's summary contains **18 source files, 64 capabilities and 75 assessments**. Those are observations of this revision and tool version, not fixed counts for all Requests releases.

`requests.get` accepts arbitrary keyword arguments. The report marks its contract unsupported with a variadic-input reason. Ready, conditional, unsupported and ambiguous describe interface evidence; none certifies that execution is safe.

The next recorded command deliberately tests whether selection can bypass that finding:

```sh
apizr generate rest src/requests/api.py --select get --output-dir rejected
```

It is refused and creates no bundle. A deliberate fixed-contract wrapper would be a separate design exercise, not something demonstrated in this video.

## Practice

Read `get` in `src/requests/api.py`, find its readiness reason, and explain the expected generation refusal. Identify which of doctor, scan and inspect answers each of these questions: valid setup, repository contents, and the contract of this file.

??? success "Check your reasoning"

    Doctor checks setup, scan inventories the selected source root, and inspect explains the file's supported contracts. Selecting `get` narrows the selection but leaves `**kwargs` unchanged. The useful next action is to design and review a supported boundary, rather than reinstalling Apizr or treating all discovered functions as public endpoints.

<span id="1-start-with-a-small-contract"></span>
<span id="2-follow-the-reason-rather-than-a-colour"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](rest.md)
