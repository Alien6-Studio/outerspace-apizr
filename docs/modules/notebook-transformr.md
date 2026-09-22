# Notebook Transformr

`apizr.modules.notebook_transformr.transformr.NotebookTransformr` exports code cells through nbconvert without executing them. It rejects notebook magics and shell commands and formats saved scripts with Black.

```python
from apizr.modules.notebook_transformr.transformr import NotebookTransformr

transformer = NotebookTransformr()
source, _ = transformer.convert_notebook("examples/pricing.ipynb")
transformer.save_script(source, ".output/notebook", "pricing.ipynb")
```

Dependency generation is a separate pipeline stage. Markdown, saved outputs and interactive execution state do not become API behavior. Models and external files must be provided explicitly.

## Configure a multi-cell notebook (0.3 development)

Install the `legacy` extra for the complete pipeline. The reviewed example in
`examples/complex-notebook` contains interactive exploration, deployable functions,
a JSON data file and explicit requirements:

```sh
apizr --notebook examples/complex-notebook/pricing.ipynb \
  --configuration examples/complex-notebook/configuration.yaml \
  --output-dir .output/complex-notebook
```

Its configuration is:

```yaml
notebook_transformr:
  include_tags: [deploy]
  exclude_tags: [explore]
code_analyzr:
  functions_to_analyze: quote
requirements: requirements.txt
include: [data]
```

Tag selection applies to **code cells**, in notebook order. With no selectors all
code cells are retained, preserving the existing behavior. An include list selects
cells matching any listed tag; an empty include list selects all code cells.
Exclusion always wins. Unknown requested tags, malformed selectors and selections
with no code cells fail with an explicit error. Magics and shell commands in any
retained cell still fail. Tags do not execute a cell or infer hidden notebook state.

`requirements` and `include` paths in YAML are relative to the source directory,
independent of the working directory and the configuration file location. Explicit
`--requirements` replaces the configured requirements; one or more `--include`
flags replace the configured include list. The existing resource path/collision
checks apply. Explicit requirements are retained even with `--skip-pipreqs`.

Conversion never installs application dependencies or executes notebook cells.
Dependencies between retained cells must therefore be ordinary Python, with helper
definitions before their use. Declare application dependencies explicitly and
include required data/model files; install generated requirements before starting
the trusted server. Cells depending on prior interactive state must be rewritten.
These selectors belong to the legacy conversion configuration; static modern
inspection continues to inspect all notebook code cells.
