# Notebook conversion

The supported owner in 0.4.6 is `apizr.notebooks`. Install the `notebook` extra.
The exporter uses nbconvert without executing cells, rejects magics and shell
commands, and uses Black only when explicitly saving a formatted script.

```python
from apizr.notebooks import NotebookTransformr, NotebookTransformrConfiguration

transformer = NotebookTransformr(
    NotebookTransformrConfiguration(include_tags=["deploy"], exclude_tags=["explore"])
)
source, resources = transformer.convert_notebook("model.ipynb")
transformer.save_script(source, ".output/notebook", "model.py")
```

Tag selection applies to code cells in notebook order. With no selectors all code
cells are retained. An include list selects cells matching any listed tag; an
empty include list selects all code cells. Exclusion wins. Unknown requested tags,
malformed selectors and selections with no code cells refuse. Magics and shell
commands in retained cells still refuse. Tags do not infer prior kernel state.

The modern `apizr inspect model.ipynb`, `apizr experiment inspect model.ipynb` and
`apizr generate rest model.ipynb --output-dir .output/model` workflows inspect all
code cells. To select cells for a deployment, explicitly export a reviewed script
first, then inspect that script. Declare application dependencies and resources
through the modern [exposure workflow](../getting-started/user-guide/exposure.md).
Conversion never installs dependencies or executes notebook cells.

The old `apizr.modules.notebook_transformr` imports and YAML pipeline configuration
were removed. Eighteen pre-removal notebook fixtures retain exact input hashes,
exported Python, formatted scripts and the magic refusal; these verify the move
without changing exported source or transformed evidence digests.
