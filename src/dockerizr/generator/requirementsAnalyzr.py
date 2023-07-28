import os
import logging
import subprocess

from .errorLogger import LogError
from .configuration import Configuration

apizr_requirements = [
    "gunicorn==21.2.0",
    "uvicorn[standard]",
]


class RequirementsAnalyzr:
    """Class to generate the requirements.txt file for a Python project."""

    def __init__(self, config: Configuration):
        self.config = config

    @LogError(logging)
    def generate_requirements(self) -> None:
        """Generate the requirements.txt file based on the code imports in the specified directory."""

        output_directory = os.path.join(
            self.config.project.project_path, self.config.project.main_folder
        )

        # Ensure the directory exists
        if not os.path.exists(output_directory):
            raise ValueError(
                f"The specified directory {output_directory} does not exist."
            )

        # Path to the requirements.txt file to be generated
        requirements_path = os.path.join(output_directory, "requirements.txt")

        # Check if requirements.txt already exists
        if os.path.exists(requirements_path):
            try:
                # Check if new requirements are detected
                result = subprocess.run(
                    [
                        "pipreqs",
                        "--savepath",
                        requirements_path,
                        output_directory,
                    ],
                    capture_output=True,
                    text=True,
                )
                if not result.stdout:
                    # No new requirements detected, no need to update
                    return
            except subprocess.CalledProcessError:
                raise RuntimeError(
                    "The pipreqs command failed. Ensure pipreqs is installed and the specified path is correct."
                )

        # Generate or update the requirements.txt file
        try:
            subprocess.run(
                [
                    "pipreqs",
                    "--force",
                    "--savepath",
                    requirements_path,
                    output_directory,
                ],
                check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "The pipreqs command failed. Ensure pipreqs is installed and the specified path is correct."
            )

        # Add the values from apizr_requirements to requirements.txt
        with open(requirements_path, "a") as f:
            for requirement in apizr_requirements:
                f.write(f"{requirement}\n")
