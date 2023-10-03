import argparse
import logging
import sys
from pathlib import Path

import yaml

from configuration import MainConfiguration
from prompt import ConfigPrompter
from extensions.context import Context
from extensions.engine import AutomationEngine

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)


class InvalidScriptError(Exception):
    """
    Custom exception for invalid scripts.
    """
    pass


def handle_args():
    """
    Handle command line arguments.

    Arguments are:
    - --notebook: Path to the Jupyter notebook to convert.
    - --script: Path to the Python script to convert.
    - --configuration: Path to the configuration file.
    - --output-dir: Path to the output.
    - --skip-fastapi: Skip FastAPI generation.
    - --skip-docker: Skip Dockerization.
    - --skip-pipreqs: Skip pipreqs generation.
    - --lang: Language for prompts. Default is English.
    - --force: Force using command line arguments instead of interactive prompts.

    :return: Namespace containing the arguments.
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
    parser.add_argument(
        "--output-dir", type=Path, help="Path to the output.")
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
        raise InvalidScriptError("Please provide a notebook or a script to convert.")

    if args.notebook and args.notebook == "":
        raise InvalidScriptError("Notebook path is empty.")

    if args.script and args.script == "":
        raise InvalidScriptError("Script path is empty.")

    return args


def init_context(args):
    """
    Initialize the context.
    The context is a dictionary that contains data shared across steps.

    This methods ensures that the context is properly initialized; this includes:
    - Loading the configuration file if provided
    - Setting the input path
    - Setting the output path
    - Setting the language for prompts
    - When the --force flag is provided, we skip the prompts
    """

    # Initialize context
    context: Context = Context()

    # Load Configuration when provided
    if args.force or args.configuration:
        context.prompt = False

    # Set the language for prompts
    if args.lang:
        context.lang = args.lang

    if args.configuration:
        try:
            with args.configuration.open("r") as f:
                config_data = yaml.safe_load(f)
                context.config = MainConfiguration(**config_data)
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}")
            sys.exit(1)
    elif context.prompt: # Use default configuration
        context.config = ConfigPrompter(context.lang).getConfiguration()

    # Dispatch the configuration values to each sub-configuration
    context.config.dispatch()

    # Set the input path
    if args.notebook:
        context.input_path = args.notebook
    elif args.script:
        context.input_path = args.script

    # Create the output directory if it doesn't exist
    if args.output_dir:
        context.output_dir = args.output_dir
        context.output_dir.mkdir(parents=True, exist_ok=True)

    return context


def init_engine(args, context):
    """
    Initialize the automation engine.
    The automation engine is responsible for running the steps in the correct order.
    Since the steps are independent, the order is not important.
    Users can skip steps using the command line arguments.

    @TODO: Add support for managing steps using the configuration file.
    """
    engine = AutomationEngine()
    vector = [
        "NotebookTransformrStep",
        "CodeAnalyzrStep",
        "FastApizrStep",
        "RequirementsAnalyzrStep",
        "DockerizrStep",
    ]

    # Handle the case where the user wants to skip a step
    for step_name in vector:
        if not args.notebook and step_name == "NotebookTransformrStep":
            continue
        if args.skip_fastapi and step_name == "FastApizrStep":
            continue
        if args.skip_docker and step_name == "DockerizrStep":
            continue
        if args.skip_pipreqs and step_name == "RequirementsAnalyzrStep":
            continue

        else:
            # Add the step with the appropriate context
            step_context: Context = Context()
            step_context.input_path = context.input_path
            step_context.output_dir = context.output_dir
            step_context.prompt = context.prompt
            step_context.lang = context.lang

            if context.config:
                if context.config.notebook_transformr and step_name == "NotebookTransformrStep":
                    step_context.config = context.config.notebook_transformr
                elif context.config.code_analyzr and step_name == "CodeAnalyzrStep":
                    step_context.config = context.config.code_analyzr
                elif context.config.fast_apizr and step_name == "FastApizrStep":
                    step_context.config = context.config.fast_apizr
                elif context.config.dockerizr and step_name == "DockerizrStep":
                    step_context.config = context.config.dockerizr
                # @TODO Pipreqs has not been isolated from Dockerizr yet
                elif context.config.dockerizr and step_name == "RequirementsAnalyzrStep":
                    step_context.config = context.config.dockerizr
                else:
                    step_context.config = None
            else:
                step_context.config = None

            engine.add_step(step_name, step_context)

    return engine


def main():
    """
    Main execution function.
    """
    args = handle_args()
    context = init_context(args)
    engine = init_engine(args, context)
    engine.run()


if __name__ == "__main__":
    main()
