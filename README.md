# OuterSpace Apizr

Turn existing Python functions into REST APIs or MCP tools. Inspect training
scripts and notebooks, record experiments, and compare their results.

Apizr **0.4.6** supports Python **3.11–3.15** on macOS and Linux.

[![PyPI](https://img.shields.io/pypi/v/outerspace-apizr.svg)](https://pypi.org/project/outerspace-apizr/)
[![CI](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml/badge.svg?branch=0.4.6)](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/ci.yml?query=branch%3A0.4.6)
[![Documentation](https://github.com/Alien6-Studio/outerspace-apizr/actions/workflows/site.yml/badge.svg?branch=gh-pages)](https://apizr.outerspace.sh/)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](https://apizr.outerspace.sh/about/LICENSE/)

## Install

With [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv tool install outerspace-apizr==0.4.6
apizr --version
```

![Install Apizr 0.4.6 with uv](https://apizr.outerspace.sh/assets/videos/uv-install-0.4.6.gif)

Prefer pip or Homebrew? Follow the [installation guide](https://apizr.outerspace.sh/getting-started/install/).

## Try it

Save this as `pricing.py`:

```python
def total(quantity: int, unit_price: float) -> float:
    return round(quantity * unit_price, 2)
```

Inspect the function, then generate its MCP server:

```sh
apizr inspect pricing.py
apizr generate mcp pricing.py --select total --output-dir dist/mcp
```

Apizr reads the function without running it. You choose which functions to expose.
The generated server runs them when a client calls them.

Follow the [Quickstart](https://apizr.outerspace.sh/getting-started/quickstart/)
to start a server and make your first REST or MCP calls. The
[full walkthrough](https://apizr.outerspace.sh/getting-started/introduction/)
explains how this works across a project.

## Work with experiments

Start with a training script or notebook you want to understand:

<!-- experiment-inspection:readme -->
```sh
apizr experiment inspect train.py
```

The report shows the data, parameters and calculations found in the source.
It does not train a model or invent scores.

You can then run trusted code, keep its history, compare results and share a
selected prediction function. Start with the
[Data Scientist quickstart](https://apizr.outerspace.sh/getting-started/data-science/),
or follow the [Academy](https://apizr.outerspace.sh/academy/).

## Go further

- [Track Python calls and Jupyter cells](https://apizr.outerspace.sh/getting-started/tracking/).
- [Review experiments in VS Code](https://apizr.outerspace.sh/academy/vscode/).
- [Analyze a project from an MCP client](https://apizr.outerspace.sh/reference/apizr-mcp-server/).
- [Build a service image](https://apizr.outerspace.sh/reference/oci-service-plugin/)
  or [deliver it with Attest](https://apizr.outerspace.sh/reference/attest-delivery-plugin/).

The core handles inspection and generation. Plugins are optional. Run generated
services and experiments only with code and dependencies you trust.

[Documentation](https://apizr.outerspace.sh/) ·
[Release notes](https://github.com/Alien6-Studio/outerspace-apizr/releases) ·
[Contributing](https://apizr.outerspace.sh/about/CONTRIBUTING/) ·
[Report an issue](https://github.com/Alien6-Studio/outerspace-apizr/issues)
