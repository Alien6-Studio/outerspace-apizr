---
title: "Install Apizr. Understand your setup."
description: Choose one installation method, identify its environment and read an actual inspection result.
lesson: 1
recording: 01-install
---

<p class="apizr-academy-kicker">Build interfaces · Lesson 01</p>

<span id="install-apizr-and-inspect-four-real-projects"></span>

# Install Apizr. Understand your setup.

The recording installs the same Apizr version four ways, then inspects four existing Python projects. The installation method determines how the tool is managed; the inspected source determines its readiness findings. A nonzero inspection status does not necessarily mean installation failed.

!!! abstract "By the end of this lesson"
    - Choose one of pip with venv, uv tools, pipx or Homebrew.
    - Identify the executable and version your shell uses.
    - Distinguish a successful installation from a source-contract diagnostic.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=7J6TWqAdx4Q" data-apizr-video="7J6TWqAdx4Q" data-apizr-title="Install Apizr. Understand your setup." aria-label="Play: Install Apizr. Understand your setup.">
    <img src="../../assets/videos/academy-01-youtube.jpg" width="1280" height="720" loading="lazy" alt="Lesson 01: Install Apizr. Understand your setup." />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

<!-- recording-transcript -->

## 1. Follow the installation you need

The video was recorded with **Apizr 0.4.3**, Python 3.14 and Apple Silicon. Use one method, rather than installing four competing executables. For a new installation, use the [current installation guide](../getting-started/install.md); keep its version separate from the historical commands shown in the transcript.

| Recorded method | Project and revision | Inspected file |
| --- | --- | --- |
| pip + project venv | `mahmoud/boltons`, `25.0.0` | `boltons/mathutils.py` |
| uv tool | `more-itertools/more-itertools`, `v10.7.0` | `more_itertools/recipes.py` |
| pipx | `python-humanize/humanize`, `4.12.3` | `src/humanize/number.py` |
| Homebrew | `un33k/python-slugify`, `v8.0.4` | `slugify/slugify.py` |

For example, the first recorded path is:

```sh
git clone --depth 1 --branch 25.0.0 https://github.com/mahmoud/boltons.git
cd boltons
python3.14 -m venv .venv
. .venv/bin/activate
python -m pip install outerspace-apizr==0.4.3
apizr --version
apizr inspect boltons/mathutils.py > inspection.txt
sed -n '1,15p' inspection.txt
```

The uv and pipx paths use separate tool environments. Humanize demonstrates why you must locate a package's actual source directory. In the Homebrew segment the workstation already has Apizr, so the recorded operation is `brew reinstall`; a first installation uses `brew install`.

## 2. Read the result before reinstalling

The More Itertools inspection reports an unsupported generator and variadic signatures. Reinstalling the CLI cannot change that source contract. Humanize and Slugify also have conditional findings: unresolved evidence is a result to investigate, rather than an installation diagnosis.

Inspection reads source without importing the inspected application. Dependencies required to run that application remain separate from the environment hosting the CLI.

## Practice

Choose one recorded installation path and inspect its matching project. Then perform the video's three final checks:

```sh
command -v apizr
apizr --version
apizr --help
```

Explain why an unsupported generator in `recipes.py` does not establish that uv installed Apizr incorrectly.

??? success "Check your reasoning"

    The checks identify the executable, version and available command interface. The generator finding describes the inspected Python contract. Keep the installed tool environment and the project's execution dependencies distinct; read the reason before choosing a supported interface boundary.

<span id="1-choose-what-needs-to-use-apizr"></span>
<span id="2-select-the-documented-version"></span>

[Back to the Academy](index.md) · [Continue to the next lesson](inspect.md)
