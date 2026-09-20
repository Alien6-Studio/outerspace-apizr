"""Convert notebooks without executing their cells."""

import ast
from pathlib import Path

from black import FileMode, format_str
from nbconvert import PythonExporter
from nbformat import ValidationError

from src.modules.notebook_transformr.configuration import (
    NotebookTransformrConfiguration,
)


class NotebookTransformr:
    def __init__(self, configuration=None):
        self.configuration = configuration or NotebookTransformrConfiguration()
        self.exporter = PythonExporter()

    async def read_file(self, file):
        return await file.read()

    def convert_notebook(self, content):
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
        output_path.write_text(
            format_str("\n".join(lines), mode=FileMode()),
            encoding=self.configuration.encoding,
        )
        return str(output_path)
