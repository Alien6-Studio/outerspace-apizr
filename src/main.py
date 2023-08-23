import logging

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)

logger = logging.getLogger(__name__)

import sys
import argparse

from .notebook_transformr.transformr import NotebookTransformr
from .code_analyzr.analyzr import AstAnalyzr
from .fast_apizr.generator import FastApiAppGenerator
from .dockerizr.generator import GunicornGenerator
from .dockerizr.generator import RequirementsAnalyzr
from .dockerizr.generator import DockerfileGenerator

def main():
    parser = argparse.ArgumentParser(description="Convert a Jupyter notebook or a Python script to a container.")
    parser.add_argument('--notebook', type=str, help="Path to the Jupyter notebook to convert.")
    parser.add_argument('--script', type=str, help="Path to the Python script to convert.")
    
    args = parser.parse_args()

    if args.notebook:
        code = convert_notebook_to_code(args.notebook)
        process_code(code)
    elif args.script:
        with open(args.script, 'r') as script_file:
            code = script_file.read()
        process_code(code, script_name=args.script, output=args.output)
    else:
        print("Please provide a notebook or a script to convert.")

def convert_notebook_to_code(notebook_path):
    """
    Converts a Jupyter notebook to Python code.
    """
    transformr = NotebookTransformr()

    with open(notebook_path, 'r') as f:
        content = f.read()
    code, _ = transformr.convert_notebook(content)
    return code

def process_code(code, script_name=None, output=None):
    # Generate Metadata from code
    analyzer = AstAnalyzr(code)
    metadata = analyzer.get_analyse()

    config_data = {
                    "module_name": script_name.replace(".json", ""),
                    "host": "0.0.0.0",
                    "port": 5000,
                    "debug": False,
                    "api_filename": "app.py"
                }

    json_data = {}
    json_data['conf'] = config_data
    json_data['analyse'] = metadata
    
    # Generate FastAPI app
    generator = FastApiAppGenerator(metadata)
    result = generator.generate_app()

    if output:
        try:
            with open(output, "w") as f:
                f.write(result)
            logger.info(f"Generated FastAPI code saved to {output}")
        except Exception as e:
            logger.error(f"Error writing to output file: {e}")
    else:
        print(result)

if __name__ == "__main__":
    main()