import logging
import argparse
import sys
import json
from generator import FastApiAppGenerator

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)

# Import necessary typing modules
from typing import Any, Dict, List, Union


# Class to convert dictionaries to objects
class ConfigObject:
    conf: Any
    analyse: Any

    def __init__(self, dictionary: Dict[str, Union["ConfigObject", List[Any], Any]]):
        for key, value in dictionary.items():
            if isinstance(value, dict):
                setattr(self, key, ConfigObject(value))
            elif isinstance(value, list):
                setattr(
                    self,
                    key,
                    [
                        ConfigObject(item) if isinstance(item, dict) else item
                        for item in value
                    ],
                )
            else:
                setattr(self, key, value)


def main():
    parser = argparse.ArgumentParser(
        description="Generate FastAPI code from JSON configurations."
    )
    parser.add_argument("file", help="Path to the JSON file with configurations.")
    parser.add_argument(
        "--output",
        default=None,
        help="Path to save the generated FastAPI code. If not specified, prints to console.",
    )

    args = parser.parse_args()

    try:
        with open(args.file, "r") as f:
            config_dict = json.load(f)
            config = ConfigObject(config_dict)

            # Validate that required attributes are present
            if not all(hasattr(config, attr) for attr in ["conf", "analyse"]):
                logger.error(
                    "Error: The JSON file must contain both 'conf' and 'analyse' keys."
                )
                sys.exit(1)

            # Add assertions for type-checking purposes
            assert hasattr(config, "conf")
            assert hasattr(config, "analyse")

            conf = config.conf
            analyse = config.analyse

    except Exception as e:
        logger.error(f"Error reading or validating JSON file: {e}")
        sys.exit(1)

    try:
        result = FastApiAppGenerator(conf, analyse).gen_fastapi_app()

    except Exception as e:
        logger.error(f"Error generating FastAPI code: {e}")
        sys.exit(1)

    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(result)
            logger.info(f"Generated FastAPI code saved to {args.output}")
        except Exception as e:
            logger.error(f"Error writing to output file: {e}")
    else:
        print(result)


if __name__ == "__main__":
    main()
