# Notebook Transformr

`apizr.modules.notebook_transformr.transformr.NotebookTransformr` exports code cells through nbconvert without executing them. It rejects notebook magics and shell commands and formats saved scripts with Black.

```python
from apizr.modules.notebook_transformr.transformr import NotebookTransformr

transformer = NotebookTransformr()
source, _ = transformer.convert_notebook("examples/pricing.ipynb")
transformer.save_script(source, ".output/notebook", "pricing.ipynb")
```

Dependency generation is a separate pipeline stage. Markdown, saved outputs and interactive execution state do not become API behavior. Models and external files must be provided explicitly.
