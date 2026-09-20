import argparse
import json
import logging
import os
import sys

import yaml

from apizr.modules.fast_apizr.configuration import FastApizrConfiguration
from apizr.modules.fast_apizr.generator import FastApiAppGenerator
from apizr.modules.fast_apizr.generator.analyzr import Analyzr
from apizr.modules.fast_apizr.prompt import ConfigPrompter
from apizr.output import output_path
from apizr.runtime import parse_python_target, python_target_argument

# Configure logging settings
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """
    Custom exception for configuration-related errors.
    """


def set_configuration(args) -> FastApizrConfiguration:
    """
    Set the configuration for fast apizr based on provided arguments.

    :param args: Arguments passed to the script.
    :return: Configured FastApizrConfiguration object.
    """
    configuration = FastApizrConfiguration()

    if not (args.force or args.configuration):
        # Use prompt mode
        return ConfigPrompter(lang=args.lang).getConfiguration()

    # Update Configuration object with the provided configuration file
    if args.configuration:
        try:
            with open(args.configuration, "r") as f:
                data = yaml.safe_load(f)
                configuration = FastApizrConfiguration(**data)
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}")
            sys.exit(1)

    # Override Configuration object with the provided arguments
    if args.version:
        configuration.python_version = parse_python_target(args.version)

    if args.encoding:
        configuration.encoding = args.encoding

    if args.module_name:
        configuration.module_name = args.module_name

    if args.api_filename:
        configuration.api_filename = args.api_filename

    return configuration


def handle_args():
    """
    Parse and handle command-line arguments.

    :param args: Arguments passed to the script.
    :return: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Generate FastAPI code.")
    parser.add_argument("file", help="Path to the Metadata file to convert")
    parser.add_argument(
        "--configuration",
        default=None,
        help="Path to the configuration file. If not specified, uses the default configuration.",
    )
    parser.add_argument(
        "--version",
        type=python_target_argument,
        default=None,
        help="Python version to use for analysis. Defaults to the running interpreter.",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="Encoding of the file. Default is utf-8.",
    )
    parser.add_argument(
        "--module_name",
        default=None,
        help="Name of the module. Default is main.",
    )
    parser.add_argument(
        "--api_filename",
        default=None,
        help="Name of the generated file. Default is app.py.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the analysis result as JSON. If not specified, prints to console.",
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
    return parser.parse_args()


def read_file(file_path):
    """
    Read the content of a file with the specified encoding.

    :param file_path: Path to the file.
    :return: Content of the file.
    """
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        raise ConfigurationError(e) from e


def save_result(output_path, result):
    """
    Save the analysis result to a specified file.

    :param output_path: Path to the output file.
    :param result: Analysis result to save.
    """

    try:
        print(f"Saving result to {output_path}")
        with open(output_path, "x") as f:
            f.write(result)
    except Exception as e:
        logger.error(f"Error writing to output file: {e}")
        raise ConfigurationError(e) from e


def main():
    try:
        args = handle_args()
        configuration: FastApizrConfiguration = set_configuration(args)
        metadata: Analyzr = Analyzr(**json.loads(read_file(args.file)))

        result = FastApiAppGenerator(configuration, metadata).gen_fastapi_app()

        if args.output:
            os.makedirs(args.output, exist_ok=True)
            save_result(output_path(args.output, configuration.api_filename), result)
        else:
            print(result)

    except (ConfigurationError, ValueError) as e:
        logger.error(f"Error generating FastAPI code: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
