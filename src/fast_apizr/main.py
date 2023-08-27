import argparse
import json
import logging
import sys

import yaml
from generator import FastApiAppGenerator
from generator.analyzr import Analyzr

from configuration import FastApizrConfiguration

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """
    Custom exception for configuration-related errors.
    """

    pass


def set_configuration(args) -> FastApizrConfiguration:
    """
    Set the configuration for fast apizr based on provided arguments.

    :param args: Arguments passed to the script.
    :return: Configured FastApizrConfiguration object.
    """
    configuration = FastApizrConfiguration()

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
        configuration.python_version = tuple(map(int, args.version.split(".")))

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
        default="3.8",
        help="Python version to use for analysis. Default is 3.8.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Encoding of the file. Default is utf-8.",
    )
    parser.add_argument(
        "--module_name",
        default="main",
        help="Name of the module. Default is main.",
    )
    parser.add_argument(
        "--api_filename",
        default="app.py",
        help="Name of the generated file. Default is app.py.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the analysis result as JSON. If not specified, prints to console.",
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
        raise ConfigurationError(e)


def save_result(output_path, result):
    """
    Save the analysis result to a specified file.

    :param output_path: Path to the output file.
    :param result: Analysis result to save.
    """

    try:
        with open(output_path, "w") as f:
            f.write(result)
        logger.info(f"Generated FastAPI code saved to {output_path}")
    except Exception as e:
        logger.error(f"Error writing to output file: {e}")
        raise ConfigurationError(e)


def main():
    try:
        args = handle_args()
        configuration: FastApizrConfiguration = set_configuration(args)
        metadata: Analyzr = Analyzr(**json.loads(read_file(args.file)))

        result = FastApiAppGenerator(configuration, metadata).gen_fastapi_app()

        if args.output:
            save_result(args.output, result)
        else:
            print(result)

    except ConfigurationError as e:
        logger.error(f"Error generating FastAPI code: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
