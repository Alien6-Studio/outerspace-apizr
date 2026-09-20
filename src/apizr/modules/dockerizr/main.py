import argparse
import logging
import sys

import yaml

from apizr.modules.dockerizr.configuration import DockerizrConfiguration
from apizr.modules.dockerizr.generator.dockerfileGenerator import DockerfileGenerator
from apizr.modules.dockerizr.generator.gunicornGenerator import GunicornGenerator
from apizr.modules.dockerizr.generator.requirementsAnalyzr import RequirementsAnalyzr
from apizr.modules.dockerizr.prompt import ConfigPrompter
from apizr.runtime import DEFAULT_PYTHON, parse_python_target, python_target_argument

# Configure logging settings
logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """
    Custom exception for configuration-related errors.
    """


def set_configuration(args) -> DockerizrConfiguration:
    """
    Set the configuration for dockerizr based on provided arguments.

    :param args: Arguments passed to the script.
    :return: Configured DockerizrConfiguration object.
    """

    configuration = DockerizrConfiguration()

    if not (args.force or args.configuration):
        # Use prompt mode
        major, minor = (
            map(int, args.version.split(".")) if args.version else DEFAULT_PYTHON
        )
        version_tuple = (major, minor)
        return ConfigPrompter(lang=args.lang).getConfiguration(
            version=version_tuple,
            encoding=args.encoding,
            project_path=args.project_path,
        )

    if args.configuration:
        with open(args.configuration, encoding="utf-8") as file:
            configuration = DockerizrConfiguration.model_validate(
                yaml.safe_load(file) or {}
            )
    if args.version:
        configuration.python_version = parse_python_target(args.version)
    if args.encoding:
        configuration.encoding = args.encoding
    if args.project_path:
        configuration.project_path = args.project_path
    if args.module_name:
        configuration.module_name = args.module_name

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
        "--project_path",
        help="Project path. Default is the current directory.",
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
    parser.add_argument(
        "--module_name", help="Generated FastAPI module name (default: app)"
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
            RequirementsAnalyzr(configuration).generate_requirements()
            DockerfileGenerator(configuration).generate_dockerfile()

    except (ConfigurationError, ValueError, OSError) as e:
        logger.error(f"Error containerizing code: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
