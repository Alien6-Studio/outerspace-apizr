# Legacy pipeline plugins

0.3 supports independently packaged extensions to the notebook/script generation
pipeline. Install a reviewed extension in the same Python environment as Apizr,
then explicitly select its entry-point name with `--plugin NAME` (repeatable), or
`convert(..., plugins=["name"])`. Installed extensions and YAML options alone never
activate a plugin. The HTTP upload API and modern Scan/Readiness/Exposure commands
do not activate these hooks.

Plugins are trusted Python code with the generator process's permissions. Loading
one imports its module and calls its code. They are not governed execution workers
or a sandbox. Their compatibility boundary is `apizr.pipeline.v1`; they cannot
redefine modern canonical contract meanings through this API.

## Package an extension

Register a class under the versioned entry-point group in the extension's own
`pyproject.toml`:

```toml
[project.entry-points."apizr.pipeline.v1"]
delivery-note = "apizr_example_note:DeliveryNote"
```

```python
from apizr.extensions.plugins.api import PipelinePlugin


class DeliveryNote(PipelinePlugin):
    api_version = 1
    after = "FastApizrStep"

    def execute(self, context):
        context.result = ("delivery_note", context.options.get("project", "sample"))
        context.write_output("delivery_note", "delivery.txt")
        return context
```

The complete installable example is
[`examples/pipeline-plugin`](https://github.com/Alien6-Studio/outerspace-apizr/tree/master/examples/pipeline-plugin).
From a checkout, install it with `python -m pip install ./examples/pipeline-plugin`.
It emits `delivery.json` using the generated API module name and a project option:

```yaml
plugin_options:
  delivery-note:
    project: pricing
```

```sh
apizr --notebook examples/pricing.ipynb --configuration plugin.yaml \
  --plugin delivery-note --output-dir .output/extended-pricing
```

Use the same environment for installation and `apizr`. Compatible v1 classes
subclass `PipelinePlugin`, implement `execute(context)` and declare an enabled
anchor in `after`. The available anchors, in pipeline order, are
`NotebookTransformrStep`, `CodeAnalyzrStep`, `FastApizrStep`,
`RequirementsAnalyzrStep` and `DockerizrStep`. Flags that omit an anchor make an
extension requesting that anchor fail explicitly. The default anchor is
`DockerizrStep`. Plugins sharing an anchor run in command-line selection order.
Core stages are never replaced; the registry is local to each conversion.

## Context and failures

`context.input_path` is the current source, `source_dir` the original source
directory, `output_dir` the generated project, `data` the accumulated core/plugin
results, `options` that plugin's JSON-compatible configuration, and `config` the
validated main configuration. Use `context.result = (key, value)` to contribute
data, and `context.write_output(key, relative_path)` to create an output file
exclusively. Do not overwrite another stage's files.

Return a `Context` retaining the output directory. A changed input must be an
existing file inside it, so an extension can explicitly transform the source for
later stages. Methods and attributes of internal core classes are not part of this
extension contract. Resource inclusion runs after the pipeline hooks; optional
Docker image construction runs last. Generated applications do not need the
plugin installed unless it deliberately adds a runtime dependency.

Missing/ambiguous entry-point names, duplicate selections, unsupported API versions,
disabled anchors and malformed results fail rather than silently falling back.
Plugin exceptions stop conversion with a named error; partial output is retained
for diagnosis, and subsequent runs require a new or explicitly cleared directory.
Pin the extension and Apizr versions in the build environment and test your extension
on supported Python versions. A future incompatible API uses a different group.
