import argparse
import logging
import sys

import yaml
from analyzr import AstAnalyzr

from configuration import CodeAnalyzrConfiguration

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


def set_configuration(args) -> CodeAnalyzrConfiguration:
    """
    Set the configuration for code analysis based on provided arguments.

    :param args: Arguments passed to the script.
    :return: Configured CodeAnalyzrConfiguration object.
    """
    configuration = CodeAnalyzrConfiguration()

    # Update Configuration object with the provided configuration file
    if args.configuration:
        try:
            with open(args.configuration, "r") as f:
                data = yaml.safe_load(f)
                configuration = CodeAnalyzrConfiguration(**data)
        except Exception as e:
            logger.error(f"Error reading configuration file: {e}")
            sys.exit(1)

    # Override Configuration object with the provided arguments
    if args.version:
        configuration.python_version = tuple(map(int, args.version.split(".")))

    if args.encoding:
        configuration.encoding = args.encoding

    if args.analyze:
        configuration.functions_to_analyze = args.analyze

    if args.ignore:
        configuration.ignore = args.ignore

    return configuration


def handle_args():
    """
    Parse and handle command-line arguments.

    :param args: Arguments passed to the script.
    :return: Parsed arguments.
    """
    parser = argparse.ArgumentParser(description="Analyse Python code.")
    parser.add_argument("file", help="Path to the Python file to analyze")
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
        "--analyze",
        default=None,
        help="Comma-separated list of functions to analyze.",
    )
    parser.add_argument(
        "--ignore",
        default=None,
        help="Comma-separated list of functions to ignore.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the analysis result as JSON. If not specified, prints to console.",
    )

    return parser.parse_args()


def read_file(file_path, encoding):
    """
    Read the content of a file with the specified encoding.

    :param file_path: Path to the file.
    :param encoding: Encoding of the file.
    :return: Content of the file.
    """
    try:
        with open(file_path, "r", encoding=encoding) as f:
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
        logger.info(f"Analysis result saved to {output_path}")
    except Exception as e:
        logger.error(f"Error writing to output file: {e}")
        raise ConfigurationError(e)


def main():
    """
    Main function to analyze a Python file based on provided arguments.

    Usage example:
    Analyze a file "example.py" with Python 3.8, encoding utf-8, and save the result in "result.json":
        python main.py example.py --version 3.8 --encoding utf-8 --output result.json

    Analyze a file "example.py", but only the functions "func1" and "func2":
        python main.py example.py --analyze func1,func2

    Analyze a file "example.py", but ignore the functions "func3" and "func4":
        python main.py example.py --ignore func3,func4
    """
    try:
        args = handle_args()
        configuration: CodeAnalyzrConfiguration = set_configuration(args)
        code = read_file(args.file, configuration.encoding)
        analyzer = AstAnalyzr(configuration=configuration, code_str=code)
        result = analyzer.get_analyse()

        if args.output:
            save_result(args.output, result)
        else:
            print(result)

    except ConfigurationError:
        sys.exit(1)


if __name__ == "__main__":
    main()
