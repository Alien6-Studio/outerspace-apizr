"""Convert notebooks without executing their cells."""

import ast
import datetime
import io
import json
import os
import sys
from pathlib import Path

from apizr.capabilities.source import (
    MAX_NOTEBOOK_BYTES,
    check_tree,
    notebook_text,
    read_notebook,
)
from apizr.environment.extras import require
from apizr.interfaces.files import write_new_text
from apizr.notebooks.configuration import (
    NotebookTransformrConfiguration,
)


class NotebookTransformr:
    def __init__(self, configuration=None):
        require("notebook", "nbconvert", "nbformat", "black", "IPython")
        from nbconvert import PythonExporter

        self.configuration = configuration or NotebookTransformrConfiguration()
        self.exporter = PythonExporter()

    async def read_file(self, file):
        return await file.read()

    def convert_notebook(self, content):
        from nbformat import ValidationError, reads, validate

        # nbformat assumes a mapping and otherwise raises an internal AttributeError.
        filename = None
        if isinstance(content, (str, Path)):
            filename = str(content)
            raw = notebook_text(read_notebook(content))
            content = io.StringIO(raw)
        else:
            raw = notebook_text(content.read(MAX_NOTEBOOK_BYTES + 1))
            content = io.StringIO(raw)
        if not isinstance(json.loads(raw), dict):
            raise ValueError("Invalid notebook structure: expected a JSON object")
        try:
            include = set(self.configuration.include_tags)
            exclude = set(self.configuration.exclude_tags)
            if include or exclude:
                notebook = reads(raw, as_version=4)
                validate(notebook)
                known = {
                    tag
                    for cell in notebook.cells
                    if cell.cell_type == "code"
                    for tag in cell.metadata.get("tags", [])
                }
                missing = (include | exclude) - known
                if missing:
                    raise ValueError(
                        "Notebook code-cell tags not found: "
                        + ", ".join(sorted(missing))
                    )
                notebook.cells = [
                    cell
                    for cell in notebook.cells
                    if cell.cell_type != "code"
                    or (
                        (
                            not include
                            or include.intersection(cell.metadata.get("tags", []))
                        )
                        and not exclude.intersection(cell.metadata.get("tags", []))
                    )
                ]
                if not any(cell.cell_type == "code" for cell in notebook.cells):
                    raise ValueError("Notebook selection contains no code cells")
                source, resources = self.exporter.from_notebook_node(notebook)
            else:
                resources = None
                if filename is not None:
                    # Keep nbconvert's filename metadata while exporting the
                    # already admitted snapshot, without reopening source bytes.
                    directory, basename = os.path.split(filename)
                    modified = datetime.datetime.fromtimestamp(
                        os.path.getmtime(filename), tz=datetime.timezone.utc
                    )
                    date_format = (
                        "%B %d, %Y" if sys.platform == "win32" else "%B %-d, %Y"
                    )
                    resources = {
                        "metadata": {
                            "name": os.path.splitext(basename)[0],
                            "path": directory,
                            "modified_date": modified.strftime(date_format),
                        }
                    }
                source, resources = self.exporter.from_file(
                    content, resources=resources
                )
        except ValidationError as exc:
            raise ValueError("Invalid notebook structure") from exc
        tree = ast.parse(source)
        check_tree(tree)
        if any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "get_ipython"
            for n in ast.walk(tree)
        ):
            raise ValueError(
                "Notebook magics and shell commands are not supported; convert them to ordinary Python first"
            )
        return source, resources

    def save_script(self, source, output_directory, filename):
        from black import FileMode, format_str

        directory = Path(output_directory)
        directory.mkdir(parents=True, exist_ok=True)
        if Path(filename).name != filename or "\\" in filename:
            raise ValueError("Expected a filename without directory components")
        output_path = directory / (Path(filename).stem + ".py")
        lines = [
            line
            for line in source.splitlines()
            if not line.startswith(("#!", "# coding:", "# In["))
        ]
        formatted = format_str("\n".join(lines), mode=FileMode())
        write_new_text(output_path, formatted, encoding=self.configuration.encoding)
        return str(output_path)
