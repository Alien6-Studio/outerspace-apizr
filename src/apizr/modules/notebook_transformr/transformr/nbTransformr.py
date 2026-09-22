"""Convert notebooks without executing their cells."""

import ast
import io
import json
from pathlib import Path

from apizr.modules.notebook_transformr.configuration import (
    NotebookTransformrConfiguration,
)
from apizr.optional import require
from apizr.output import write_new_text


class NotebookTransformr:
    def __init__(self, configuration=None):
        require("notebook", "nbconvert", "nbformat", "black", "IPython")
        from nbconvert import PythonExporter

        self.configuration = configuration or NotebookTransformrConfiguration()
        self.exporter = PythonExporter()

    async def read_file(self, file):
        return await file.read()

    def convert_notebook(self, content):
        from nbformat import ValidationError

        # nbformat assumes a mapping and otherwise raises an internal AttributeError.
        if isinstance(content, (str, Path)):
            raw = Path(content).read_text(encoding="utf-8")
        else:
            raw = content.read()
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            content = io.StringIO(raw)
        if not isinstance(json.loads(raw), dict):
            raise ValueError("Invalid notebook structure: expected a JSON object")
        try:
            source, resources = (
                self.exporter.from_filename(str(content))
                if isinstance(content, (str, Path))
                else self.exporter.from_file(content)
            )
        except ValidationError as exc:
            raise ValueError("Invalid notebook structure") from exc
        tree = ast.parse(source)
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
