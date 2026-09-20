import logging
import os
import subprocess  # nosec B404 since there is no alternative to subprocess

from configuration import DockerizrConfiguration

from .errorLogger import LogError


class RequirementsAnalyzr:
    """Class to generate the requirements.txt file for a Python project."""

    def __init__(self, config: DockerizrConfiguration):
        self.config = config

    def remove_duplicates_preserving_order(self, filename):
        with open(filename, "r") as f:
            lines = f.readlines()

        seen = set()
        unique_lines = []

        for line in lines:
            line_stripped = line.strip()  # Strip whitespaces to ensure accurate comparison
            if line_stripped not in seen:
                unique_lines.append(line)
                seen.add(line_stripped)

        with open(filename, "w") as f:
            f.writelines(unique_lines)

    @LogError(logging)
    def generate_requirements(self) -> None:
        """Generate the requirements.txt file based on the code imports in the specified directory."""
        output_directory = self.config.project_path

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
                    args=[
                        "pipreqs",
                        "--savepath",
                        requirements_path,
                        output_directory,
                    ],
                    shell=False,  # nosec B602, B603
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
                args=[
                    "pipreqs",
                    "--force",
                    "--savepath",
                    requirements_path,
                    output_directory,
                ],
                shell=False,  # nosec B602, B603
                check=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "The pipreqs command failed. Ensure pipreqs is installed and the specified path is correct."
            )

        # Add the values from apizr_requirements to requirements.txt
        with open(requirements_path, "a") as f:
            for requirement in self.config.apizr_requirements:
                f.write(f"{requirement}\n")

        # Remove duplicates
        self.remove_duplicates_preserving_order(requirements_path)