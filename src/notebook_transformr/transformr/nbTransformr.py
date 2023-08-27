import os
import subprocess  # nosec B404 since there is no alternative to subprocess
from itertools import groupby

from black import FileMode, format_str
from nbconvert import PythonExporter

from configuration import NotebookTransformrConfiguration


class NotebookTransformr:
    def __init__(self, configuration: NotebookTransformrConfiguration):
        self.configuration = configuration
        self.exporter = PythonExporter()

    async def read_file(self, file):
        return await file.read()

    def convert_notebook(self, content):
        return self.exporter.from_file(content)

    def generate_requirements(self, output_directory):
        # Generate requirements.txt using pipreqs shell command
        requirements_path = os.path.join(output_directory, "requirements.txt")
        subprocess.run(
            args=[
                "pipreqs",
                "--force",
                "--savepath",
                requirements_path,
                output_directory,
            ],
            shell=True,  # B603 recommended by Bandit
        )

    def save_script(self, source, output_directory, filename):
        if not os.path.isdir(output_directory):
            os.makedirs(output_directory)
        output_path = os.path.join(output_directory, f"{filename.rsplit('.', 1)[0]}.py")

        # Split the source by lines and filter unwanted lines
        lines = source.split("\n")
        filtered_lines = [
            line
            for line in lines
            if not line.startswith("#!")
            and not line.startswith("# coding:")
            and not line.startswith("# In[")
        ]

        # Remove consecutive empty lines
        compressed_lines = [
            filtered_lines[i]
            for i in range(len(filtered_lines))
            if filtered_lines[i].strip() or (i > 0 and filtered_lines[i - 1].strip())
        ]

        # Join the compressed lines back together
        compressed_source = "\n".join(compressed_lines)

        # Format the compressed source using Black
        formatted_source = format_str(compressed_source, mode=FileMode())

        # Call the generate_requirements method to create requirements.txt
        self.generate_requirements(output_directory)

        with open(output_path, "w", encoding=self.configuration.encoding) as f:
            f.write(formatted_source)  # Write the formatted source code

        return output_path
