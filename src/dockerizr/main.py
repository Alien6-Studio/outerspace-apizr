import argparse
import logging
import sys

import yaml
from generator.dockerfileGenerator import DockerfileGenerator
from generator.gunicornGenerator import GunicornGenerator
from generator.requirementsAnalyzr import RequirementsAnalyzr

from configuration import DockerizrConfiguration

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


def set_configuration(args) -> DockerizrConfiguration:
    """
    Set the configuration for dockerizr based on provided arguments.

    :param args: Arguments passed to the script.
    :return: Configured DockerizrConfiguration object.
    """

    configuration = DockerizrConfiguration()

    # Update Configuration object with the provided configuration file
    if args.configuration:
        try:
            with open(args.configuration, "r") as f:
                data = yaml.safe_load(f)
                configuration = DockerizrConfiguration(**data)
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}")
            sys.exit(1)

    # Override Configuration object with the provided arguments
    if args.version:
        configuration.python_version = tuple(map(int, args.version.split(".")))

    if args.encoding:
        configuration.encoding = args.encoding

    if args.project_path:
        configuration.project_path = args.project_path

    return configuration


def handle_args():
    """
    Parse and handle command-line arguments.

    :param args: Arguments passed to the script.
    :return: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Containerize Code.")
    parser.add_argument(
        "--configuration",
        help="Path to the configuration file. If not specified, uses the default configuration.",
    )
    parser.add_argument(
        "--action",
        choices=["gunicorn", "requirements", "dockerfile"],
        help="Choose the action to perform: generate Gunicorn files, requirements.txt, or Dockerfile.",
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
        "--project_path",
        help="Project path. Default is the current directory.",
    )

    return parser.parse_args()


def main():
    try:
        args = handle_args()
        configuration: DockerizrConfiguration = set_configuration(args)

        if args.action == "gunicorn":
            GunicornGenerator(configuration).generate_gunicorn()
        elif args.action == "requirements":
            RequirementsAnalyzr(configuration).generate_requirements()
        elif args.action == "dockerfile":
            DockerfileGenerator(configuration).generate_dockerfile()
        else:  # do all actions
            GunicornGenerator(configuration).generate_gunicorn()
            RequirementsAnalyzr(configuration).generate_requirements()
            DockerfileGenerator(configuration).generate_dockerfile()

    except ConfigurationError as e:
        logger.error(f"Error containerizing code: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
