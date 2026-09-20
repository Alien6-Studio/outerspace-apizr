# Start here

<span id="introduction"></span>

Apizr converts functions from Python scripts and Jupyter notebooks into FastAPI
applications and Docker projects. Start with the complete workflow; individual
pipeline stages are available in the technical reference when you need them.

## Install the development checkout

Use Python **3.11–3.14** and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
git clone https://github.com/Alien6-Studio/outerspace-apizr.git
cd outerspace-apizr
uv sync --locked
```

The 0.2.0 documentation describes the development checkout. Publishing a new
version to PyPI is a separate maintainer action.

## Choose your next step

- **Convert a notebook or script:** follow [Generate an API and container](user-guide/apizr.md).
- **Upgrade from 0.1.x:** read the [migration notes](developer-guide/releases.md).
- **Use individual commands, Python components or HTTP endpoints:** open the [technical reference](../reference/index.md).
- **Change Apizr itself:** use [Contributing](../about/CONTRIBUTING.md).

Generation analyzes source without executing it. Starting or importing the
generated application executes the original module, so run generated applications
only from trusted source code.
