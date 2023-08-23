import logging
import argparse
import json
import sys
from generator import Configuration

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)


# Class to convert dictionaries to objects
class ConfigObject:
    def __init__(self, dictionary):
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
        description="Interact with FastAPI app for dockerizr."
    )
    parser.add_argument("file", help="Path to the JSON file with configurations.")
    parser.add_argument(
        "--action",
        choices=["gunicorn", "requirements", "dockerfile"],
        required=True,
        help="Choose the action to perform: generate Gunicorn files, requirements.txt, or Dockerfile.",
    )

    args = parser.parse_args()

    try:
        with open(args.file, "r") as f:
            config_dict = json.load(f)
            config = ConfigObject(config_dict)
            conf = Configuration(
                **vars(config)
            )  # Convert ConfigObject to Configuration

            if args.action == "gunicorn":
                from app import generate_gunicorn_files

                generate_gunicorn_files(conf)
            elif args.action == "requirements":
                from app import generate_requirements_txt

                generate_requirements_txt(conf)
            elif args.action == "dockerfile":
                from app import generate_dockerfile

                generate_dockerfile(conf)

    except Exception as e:
        logger.error(f"Error during {args.action} generation: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
