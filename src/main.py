import argparse
import importlib
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import yaml

from code_analyzr.analyzr.astAnalyzr import AstAnalyzr
from code_analyzr.configuration import CodeAnalyzrConfiguration
from configuration import MainConfiguration
from dockerizr.configuration import DockerizrConfiguration
from dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from dockerizr.generator.gunicornGenerator import GunicornGenerator
from dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr
from exceptions import (
    DockerizationError,
    FastApiGenerationError,
    InvalidNotebookError,
    InvalidScriptError,
    MetadataGenerationError,
)
from fast_apizr.configuration import FastApizrConfiguration
from fast_apizr.generator.analyzr import Analyzr as FastApiAnalyzr
from fast_apizr.generator.exceptions import FastApiAlreadyImplementedException
from fast_apizr.generator.fastApiAppGenerator import FastApiAppGenerator
from notebook_transformr.configuration import NotebookTransformrConfiguration
from notebook_transformr.transformr.nbTransformr import NotebookTransformr
from prompt import ConfigPrompter

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)


HOSTNAME = "0.0.0.0"  # nosec B104


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
    parser.add_argument(
        "--configuration", type=Path, help="Path to the configuration file."
    )
    parser.add_argument("--output", type=Path, help="Path to the output.")
    parser.add_argument(
        "--skip-fastapi", action="store_true", help="Skip FastAPI generation."
    )
    parser.add_argument(
        "--skip-docker", action="store_true", help="Skip Dockerization."
    )
    parser.add_argument(
        "--skip-pipreqs", action="store_true", help="Skip pipreqs generation."
    )
    parser.add_argument(
        "--lang",
        default="en",
        choices=["en", "fr"],
        help="Language for prompts. Default is English.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force using command line arguments instead of interactive prompts.",
    )
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


def is_local_module(module_name, input_path):
    """
    Check if a module is a local module or a standard/package module.
    """
    try:
        # Try to import the module (this check fails)
        result = importlib.import_module(module_name)
        return input_path in result.__file__
    except ImportError:
        return True


def process_input(
    configuration: MainConfiguration,
    input_path: Path,
    output: Path,
    skip_fastapi: bool,
    skip_docker: bool,
    skip_pipreqs: bool,
    language: str,
    prompt: bool = True,
):
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
        code, script_name = convert_notebook_to_code(
            configuration=configuration.notebook_transformr,
            notebook_path=destination_path,
            output=output,
        )
    else:
        with destination_path.open("r") as script_file:
            code = script_file.read()
        script_name = input_path.name

    try:
        if prompt:
            configuration = ConfigPrompter(
                code, lang=language, script_name=script_name
            ).getConfiguration(output_path=output)
        process_code(
            configuration=configuration,
            code=code,
            script_name=script_name,
            output=output,
            skip_fastapi=skip_fastapi,
            input_path=input_path,
        )
    except MetadataGenerationError:
        logger.error(f"Failed to generate metadata from code in {script_name}")
        sys.exit(1)
    except FastApiGenerationError:
        logger.error(f"Failed to generate FastAPI app from {script_name}")
        sys.exit(1)

    if not skip_docker:
        dockerize_app(
            configuration=configuration.dockerizr,
            script_name=script_name,
            output=output,
            skip_pipreqs=skip_pipreqs,
        )


def convert_notebook_to_code(
    configuration: NotebookTransformrConfiguration, notebook_path: Path, output: Path
) -> tuple:
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

    if configuration:
        nb_configuration = configuration
    else:
        nb_configuration = NotebookTransformrConfiguration()

    transformr = NotebookTransformr(nb_configuration)

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


def process_code(
    configuration: MainConfiguration,
    code: str,
    script_name: str,
    output: Path,
    skip_fastapi: bool,
    input_path=Path,
):
    """
    Processes the given Python code to generate a corresponding FastAPI application.
    """

    if not script_name:
        logger.error("Script name not provided.")
        return

    if not output:
        logger.error("Output path not provided.")
        return

    if skip_fastapi:
        logger.info("Skipping FastAPI generation.")

        # Rename the script to `<basename>-api.py``
        api_filename = os.path.basename(script_name).replace(".py", "_api.py")
        output_api_filepath = output / api_filename
        shutil.move(output / script_name, output_api_filepath)
        return

    # Generate Metadata from code
    try:
        if configuration.code_analyzr:
            code_analyzr_configuration = configuration.code_analyzr
        else:
            code_analyzr_configuration = CodeAnalyzrConfiguration()

        metadata = AstAnalyzr(code_analyzr_configuration, code).get_analyse()
        json_metadata = json.loads(metadata)

        # Check imports for local modules
        for import_data in json_metadata["imports_from"]:
            module_name = import_data["module"]
            if is_local_module(module_name, os.path.abspath(input_path.parent)):
                s = str(Path(input_path.parent, module_name)).split(".")[0]
                local_module_path = Path(s)
                dest_path = Path(output, s)
                local_file = Path(module_name + ".py")

                # Case where the module is a directory
                if local_module_path.exists() and not dest_path.exists():
                    dest_path = Path(output, local_module_path.name)
                    shutil.copytree(local_module_path, dest_path)

                # Case where the module is a file
                elif local_file.exists():
                    shutil.copy(local_file, output)

    except Exception as e:
        logger.error("Error generating metadata from code.")
        raise MetadataGenerationError(
            f"Failed to generate metadata from code: {str(e)}"
        ) from e

    api_filename = os.path.basename(script_name).replace(".py", "_api.py")
    if configuration.fast_apizr:
        fast_apizr_configuration = configuration.fast_apizr
    else:
        fast_apizr_configuration: FastApizrConfiguration = (
            FastApizrConfiguration.model_validate(
                {
                    "module_name": script_name.replace(".py", ""),
                    "api_filename": api_filename,
                }
            )
        )

    # Generate FastAPI app
    try:
        content = FastApiAnalyzr.model_validate_json(metadata)
        result = FastApiAppGenerator(
            fast_apizr_configuration, content
        ).gen_fastapi_app()
    except FastApiAlreadyImplementedException:
        logger.info("FastAPI is already imported in the provided code.")
        result = code

        # Rename the script to `<basename>-api.py``
        api_filename = os.path.basename(script_name).replace(".py", "_api.py")
        output_api_filepath = output / api_filename
        shutil.move(output / script_name, output_api_filepath)
        return
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


def dockerize_app(
    configuration: DockerizrConfiguration,
    script_name: str,
    output: Path,
    skip_pipreqs: bool,
):
    """
    Dockerizes the provided FastAPI application.
    """

    # Prepare API filename and configuration
    api_filename = script_name.replace(".py", "_api.py")

    # Set the project path to the absolute path of the output directory
    configuration.api_filename = api_filename
    configuration.project_path = str(output.resolve())

    try:
        # Generate necessary files for dockerization
        if not skip_pipreqs:
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
    configuration = MainConfiguration()

    try:
        args = handle_args()

        if args.configuration:
            try:
                with args.configuration.open("r") as f:
                    config_data = yaml.safe_load(f)
                    configuration = MainConfiguration(**config_data)
            except Exception as e:
                logger.error(f"Error reading configuration file: {e}")
                sys.exit(1)

        # Create the output directory if it doesn't exist
        args.output.mkdir(parents=True, exist_ok=True)

        if args.notebook:
            process_input(
                configuration=configuration,
                input_path=args.notebook,
                output=args.output,
                skip_fastapi=args.skip_fastapi,
                skip_docker=args.skip_docker,
                skip_pipreqs=args.skip_pipreqs,
                language=args.lang,
                prompt=not (args.force or args.configuration),
            )
        elif args.script:
            process_input(
                configuration=configuration,
                input_path=args.script,
                output=args.output,
                skip_fastapi=args.skip_fastapi,
                skip_docker=args.skip_docker,
                skip_pipreqs=args.skip_pipreqs,
                language=args.lang,
                prompt=not (args.force or args.configuration),
            )

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
