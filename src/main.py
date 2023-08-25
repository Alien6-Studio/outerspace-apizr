import logging
import os
import sys
import argparse
import shutil

from pathlib import Path

from notebook_transformr.transformr.nbTransformr import NotebookTransformr
from code_analyzr.analyzr.astAnalyzr import AstAnalyzr

from fast_apizr.generator.configuration import Configuration as FastApiConfiguration
from fast_apizr.generator.analyzr import Analyzr as FastApiAnalyzr
from fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator

from dockerizr.generator.configuration import Configuration as DockerizrConfiguration
from dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from dockerizr.generator.gunicornGenerator import GunicornGenerator
from dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr

from exceptions import (
    InvalidNotebookError,
    InvalidScriptError,
    MetadataGenerationError,
    FastApiGenerationError,
    DockerizationError,
)

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)


def validate_input(file_path: Path):
    """
    Validate the provided input file to ensure it's either a Python notebook or script.

    Args:
        file_path (Path): Path to the input file.

    Raises:
        InvalidNotebookError: If the file is not a valid Jupyter notebook.
        InvalidScriptError: If the file is not a recognized Python script.
    """
    # Check file extension
    if file_path.suffix == ".ipynb":
        # Check if it's a valid notebook
        with file_path.open("r", encoding="utf-8") as f:
            content = f.read()
            if '"cells": [' not in content[:1000]:  # Check in the first 1000 characters
                raise InvalidNotebookError(
                    f"'{file_path}' is not a valid Jupyter notebook."
                )
    elif file_path.suffix == ".py":
        # For now, we just check the extension. In the future, you might want to add more checks
        # like checking for valid Python syntax.
        pass
    else:
        raise InvalidScriptError(
            f"'{file_path}' is not a recognized format. Please provide a .ipynb or .py file."
        )


def handle_args():
    """
    Parse and validate command line arguments.

    Parses the command line arguments to obtain the paths to the Jupyter notebook or Python script
    and the output directory. Ensures that at least one input file (notebook or script) is provided.

    Returns:
        args: Parsed command line arguments with paths to the notebook/script and output directory.

    Raises:
        ValueError: If neither a notebook nor a script is provided.
        InvalidNotebookError: If the provided notebook file is invalid.
        InvalidScriptError: If the provided script file is not recognized.
    """
    parser = argparse.ArgumentParser(
        description="Convert a Jupyter notebook or a Python script to a container."
    )
    parser.add_argument(
        "--notebook", type=Path, help="Path to the Jupyter notebook to convert."
    )
    parser.add_argument(
        "--script", type=Path, help="Path to the Python script to convert."
    )
    parser.add_argument("--output", type=Path, help="Path to the output directory.")

    args = parser.parse_args()

    if not args.notebook and not args.script:
        raise ValueError("Please provide a notebook or a script to convert.")

    if args.notebook and args.notebook == "":
        raise InvalidNotebookError("Notebook path is empty.")
    if args.script and args.script == "":
        raise InvalidScriptError("Script path is empty.")

    # Validate the input file
    try:
        if args.notebook:
            validate_input(args.notebook)
        else:
            validate_input(args.script)
    except InvalidNotebookError:
        logger.error(f"'{args.notebook}' is not a valid Jupyter notebook.")
        sys.exit(1)
    except InvalidScriptError:
        logger.error(f"'{args.script}' is not a recognized Python script.")
        sys.exit(1)

    return args


def process_input(input_path: Path, output: Path):
    """
    Process the provided input (notebook or script) for conversion and Dockerization.

    Depending on the type of the input (determined by its file extension), this function:
    1. Copies the input to the output directory.
    2. If it's a notebook, converts it to a Python script.
    3. Generates a corresponding FastAPI application from the code.
    4. Prepares the FastAPI app for Docker containerization.

    Args:
        input_path (Path): Path to the input file (notebook or script).
        output (Path): Directory where the converted and Dockerized app should be saved.

    Raises:
        MetadataGenerationError: If there's an issue generating metadata from the code.
        FastApiGenerationError: If there's an error generating the FastAPI app.
    """

    # Ensure input_path is not None
    if not input_path:
        logger.error("Input path is not provided.")
        sys.exit(1)

    destination_path = output / input_path.name
    shutil.copy(input_path, destination_path)

    if input_path.suffix == ".ipynb":
        code, script_name = convert_notebook_to_code(destination_path, output=output)
    else:
        with destination_path.open("r") as script_file:
            code = script_file.read()
        script_name = input_path.name

    try:
        process_code(code, script_name=script_name, output=output)
    except MetadataGenerationError:
        logger.error(f"Failed to generate metadata from code in {script_name}")
        sys.exit(1)
    except FastApiGenerationError:
        logger.error(f"Failed to generate FastAPI app from {script_name}")
        sys.exit(1)

    dockerize_app(script_name=script_name, output=output)


def convert_notebook_to_code(notebook_path: Path, output: Path) -> tuple:
    """
    Converts the provided Jupyter notebook into executable Python code.

    Utilizes the NotebookTransformr to convert the notebook into a Python script and saves
    the generated script in the specified output directory. The saved script has the same name
    as the original notebook but with a .py extension.

    Args:
        notebook_path (Path): Absolute path to the Jupyter notebook.
        output (Path): Directory where the converted script should be saved.

    Returns:
        tuple: Contains the extracted Python code and the name of the generated script.

    Raises:
        InvalidNotebookError: If there's an issue converting the notebook.
    """
    transformr = NotebookTransformr()
    try:
        code, _ = transformr.convert_notebook(
            notebook_path
        )  # Pass the path, not content
    except Exception as e:
        logger.error(f"Failed to convert {notebook_path} into Python code.")
        raise InvalidNotebookError(f"Error during notebook conversion: {str(e)}") from e

    script_name = notebook_path.stem + ".py"
    transformr.save_script(code, output, script_name)
    return code, script_name


def process_code(code: str, script_name: str, output: Path):
    """
    Processes the given Python code to generate a corresponding FastAPI application.
    ...
    (rest of the docstring)
    """

    if not script_name:
        logger.error("Script name not provided.")
        return

    if not output:
        logger.error("Output path not provided.")
        return

    # Generate Metadata from code
    try:
        metadata = AstAnalyzr(code).get_analyse()
    except Exception as e:
        logger.error("Error generating metadata from code.")
        raise MetadataGenerationError(
            f"Failed to generate metadata from code: {str(e)}"
        ) from e

    api_filename = os.path.basename(script_name).replace(".py", "_api.py")
    configuration: FastApiConfiguration = FastApiConfiguration.model_validate(
        {
            "module_name": script_name.replace(".py", ""),
            "api_filename": api_filename,
        }
    )

    # Generate FastAPI app
    try:
        content = FastApiAnalyzr.model_validate_json(metadata)
        result = FastApiAppGenerator(configuration, content).gen_fastapi_app()
    except Exception as e:
        logger.error("Error generating FastAPI app.")
        raise FastApiGenerationError(
            f"Failed to generate FastAPI application: {str(e)}"
        ) from e

    output_api_filepath = output / api_filename

    try:
        with output_api_filepath.open("w") as f:
            f.write(result)
        logger.info(f"Generated FastAPI code saved to {output}")
    except Exception as e:
        logger.error(f"Error writing to output file: {e}")


def dockerize_app(script_name: str, output: Path):
    """
    ... (le reste de la docstring)
    """

    # Prepare API filename and configuration
    api_filename = script_name.replace(".py", "_api.py")
    configuration: DockerizrConfiguration = DockerizrConfiguration.model_validate(
        {
            "project": {
                "main_folder": str(
                    output.resolve()
                ),  # Use the absolute path of the output directory
                "main_file": "main.py",
                "main_module": "main",
                "python_version": (3, 11),
            },
            "apizer": {"api_file_name": api_filename},
            "server": {
                "server_app": "gunicorn",
                "wsgi_file_name": "wsgi.py",
                "wsgi_conf_file_name": "gunicorn.conf.py",
            },
        }
    )

    try:
        # Generate necessary files for dockerization
        RequirementsAnalyzr(configuration).generate_requirements()
        GunicornGenerator(configuration).generate_gunicorn()
        DockerfileGenerator(configuration).generate_dockerfile()
    except Exception as e:
        logger.error(f"Error during dockerization process: {str(e)}")
        raise DockerizationError(
            f"Failed during dockerization process: {str(e)}"
        ) from e


def main():
    """
    Main execution function. Parses arguments, processes input, and generates output.
    """
    try:
        args = handle_args()

        # Create the output directory if it doesn't exist
        args.output.mkdir(parents=True, exist_ok=True)

        if args.notebook:
            process_input(args.notebook, args.output)
        elif args.script:
            process_input(args.script, args.output)
            dockerize_app(script_name=str(args.script), output=args.output)

    except (InvalidNotebookError, InvalidScriptError) as e:
        logger.error(str(e))
        print(f"Error: {str(e)}")
    except MetadataGenerationError:
        logger.error("Failed to generate metadata from code.")
        print("Error during metadata generation from code.")
    except FastApiGenerationError:
        logger.error("Failed to generate FastAPI app.")
        print("Error during FastAPI application generation.")
    except DockerizationError:
        logger.error("Failed during dockerization process.")
        print("Error during the dockerization process.")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"Unexpected error occurred: {str(e)}")


if __name__ == "__main__":
    main()
