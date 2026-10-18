# Extend Apizr with an installed program

Invoke a minimal trusted extension from the installed core without importing it
into the core environment. The result demonstrates the modern `apizr.extension/v1`
protocol and a real refused operation.

## Before you begin

Use the [core installation](../getting-started/install.md), uv and the
[downloadable extension probe](../downloads/extension-probe.zip). Extract it into
`extension-probe/` outside the Apizr checkout. This local demonstration package is
GPL-3.0-or-later and must not be published. It has no application data or external
service. These operations execute trusted local programs with user permissions.

## Prepare the separate extension environment

From the directory containing `extension-probe/`:

```sh
uv venv --python 3.11 extension-env
uv pip install --python extension-env/bin/python ./extension-probe
python extension-probe/invoke.py "$PWD/extension-env/bin/python"
```

Use the Python from your installed core environment for the last command.
The supplied `invoke.py` imports supported `apizr.capabilities` and
`apizr.extension_runtime` APIs. It derives a source digest, sends `describe` with
explicit byte/time limits and an empty environment, and checks the returned digest.
The response contains `status:"ok"` and `message:"demo extension reached"`.

## Handle an unsupported operation

The downloadable `invoke_installed.py` covers managed inventory selection and
refusal. For this standalone prepared environment, the same public API can test:

```python
from pathlib import Path
from apizr.extension_runtime import Limits, PluginFailed, invoke_extension

try:
    invoke_extension(
        Path.cwd() / "extension-env/bin/python",
        "apizr_extension_probe.runtime",
        "unknown",
        {},
        limits=Limits(wall_time_ms=3000),
        environment={},
    )
except PluginFailed as error:
    assert error.code == "plugin_failed"
else:
    raise AssertionError("Unsupported operation must be refused")
```

## Understand the extension boundary

The runtime supervises a fresh process, bounded JSON and process-group cleanup.
It grants no filesystem/network sandbox. For managed official extensions,
installation, activation and operator permissions remain independent. The
[invocation reference](../reference/extension-invocation.md) defines the wire
format, cancellation and exact failures; [local extensions](../reference/local-extensions.md)
defines verified installation and lifecycle.

This is separate from historical `apizr.pipeline.v1` plugins, which extend the
legacy pipeline. To change Apizr itself or package a new provider, use
[Contributing](../about/CONTRIBUTING.md) and its qualification rules.
Remove only `extension-env/` and the extracted probe directory when finished.
