---
title: Install Apizr in the right environment
description: Choose an installation you can explain and verify.
lesson: 1
---

<p class="apizr-academy-kicker">Build a service · Lesson 01 · Plan about 20 min</p>

# Install Apizr in the right environment

A colleague sends you a notebook and says, “I installed Apizr, but the command is missing.” Another can run the command, yet the notebook cannot import the SDK. Both may have installed the package successfully. They are using different Python environments.

Your first result is a working, identifiable installation. Keep the installation decision separate from the environment that will later run a generated service.

!!! abstract "By the end of this lesson"
    - Choose between a project environment and an isolated command-line tool.
    - Check which Python and Apizr version you are actually using.
    - Prepare the environment needed by the next lesson.

## Watch the lesson

<div class="apizr-demo-video">
  <a class="apizr-demo-video__cover" href="https://www.youtube.com/watch?v=7J6TWqAdx4Q" data-apizr-video="7J6TWqAdx4Q" data-apizr-title="Install Apizr with pip, uv, pipx or Homebrew" aria-label="Play: Install Apizr with pip, uv, pipx or Homebrew">
    <img src="../../assets/videos/tutorial-install.jpg" width="480" height="360" loading="lazy" alt="Academy Part I: install Apizr" />
    <span class="apizr-demo-video__play"><span aria-hidden="true">▶</span> Watch the tutorial</span>
  </a>
</div>

English · 6:39 · The written steps below target 0.4.6 development; the recording keeps its original demonstrated version.

## 1. Choose what needs to use Apizr

| Your task | Installation to choose | What to verify |
| --- | --- | --- |
| Import `apizr.tracking` in a script or notebook | Install in that script or kernel’s environment | That Python can import `apizr`. |
| Use the CLI across projects | An isolated uv tool or pipx installation | The `apizr` executable resolves to that tool. |
| Run a generated REST or MCP service | A separate environment for its generated requirements | Its interpreter has the service’s dependencies. |

A tool installation does not add a package to every Python interpreter. Equally, activating a project environment does not install the dependencies of a generated server.

## 2. Select the documented version

The Academy’s written exercises target **0.4.6 development**. Follow [the development installation](../development/0.4.md#install-a-development-wheel) to build the identified source revision; 0.4.6 is not a published PyPI release. The [installation guide](../getting-started/install.md) also explains the published **0.4.5** option. Earlier recordings keep the version they originally demonstrated.

After installing, keep the chosen environment active and run:

```sh
apizr --version
python -c 'import sys; print(sys.executable)'
```

For an SDK environment, also check:

```sh
python -c 'import apizr; print(apizr.__file__)'
```

A version string identifies a package version. For a development build, retain the source commit too: two source revisions can declare the same version.

## Practice

1. Install using the path appropriate to your intended use.
2. Write down the reported version, the interpreter path and whether this environment is for CLI use, SDK use or the generated service.
3. Explain why a notebook might still report `ModuleNotFoundError` after `uv tool install` succeeds. Decide where to install the package before changing `PATH`.

??? success "Check your reasoning"

    An isolated tool has its own interpreter and installed packages. Your notebook uses its selected kernel. Install the SDK into that kernel environment, or deliberately select a kernel that already contains it. Changing the shell’s `PATH` alone does not install a Python import.

    You are ready to continue when you can locate the executable and interpreter, identify their version and explain which environment will run the workload.

[Back to the Academy](index.md) · [Continue to the next lesson](inspect.md)
