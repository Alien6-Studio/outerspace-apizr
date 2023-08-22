"""
Usage example:
Generate FastAPI code for a file "config.json" and save the result in "result.py":
    python main.py config.json --output result.py
"""

import argparse
import sys
import json

from generator import FastApiAppGenerator


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
            config = json.load(f)

            # Validate that required keys are present
            if not all(key in config for key in ["conf", "analyse"]):
                print(
                    "Error: The JSON file must contain both 'conf' and 'analyse' keys."
                )
                sys.exit(1)

            conf = config["conf"]
            analyse = config["analyse"]

    except Exception as e:
        print(f"Error reading or validating JSON file: {e}")
        sys.exit(1)

    try:
        result = FastApiAppGenerator(conf, analyse).gen_fastapi_app()
    except Exception as e:
        print(f"Error generating FastAPI code: {e}")
        sys.exit(1)

    if args.output:
        try:
            with open(args.output, "w") as f:
                f.write(result)
            print(f"Generated FastAPI code saved to {args.output}")
        except Exception as e:
            print(f"Error writing to output file: {e}")
    else:
        print(result)


if __name__ == "__main__":
    main()
