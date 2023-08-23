import logging

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)

logger = logging.getLogger(__name__)

import json
import re
import os
import logging

from fastapi import FastAPI, File, HTTPException, Depends, Query
from typing import Optional
from analyzr import AstAnalyzr
from analyzr.ast_node import LogError

BASE_DIRECTORY = os.environ.get("BASE_DIRECTORY", "/app/data/")

app = FastAPI()


def validate_python_version(
    python_version: str = Query("3.8", regex="^\d+\.\d+$")
) -> tuple:
    """Validate and extract the python version."""
    return tuple(map(int, re.findall(r"[0-9]+", python_version)))


def validate_encoding(encoding: str = Query("utf-8")) -> str:
    """Validate the file encoding."""
    try:
        "test".encode().decode(encoding)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid encoding")
    return encoding


@LogError(logging)
def analyze_python_code(
    file_content: bytes,
    python_version: tuple,
    encoding: str,
    functions_to_analyze: Optional[str] = None,
    ignore: Optional[str] = None,
) -> dict:
    try:
        code_str = file_content.decode(encoding)
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unable to decode file with provided encoding",
        )

    try:
        analyzer = AstAnalyzr(
            code_str,
            functions_to_analyze=functions_to_analyze,
            ignore=ignore,
            version=python_version,
        )
        result = analyzer.get_analyse()
    except Exception:
        raise HTTPException(status_code=500, detail="Error during analysis")

    return json.loads(result)


@app.post("/analyse_file/")
async def create_file(
    python_version: tuple = Depends(validate_python_version),
    encoding: str = Depends(validate_encoding),
    functions_to_analyze: Optional[str] = None,
    ignore: Optional[str] = None,
    file: bytes = File(...),
):
    """Analyse a Python file and return its structure."""
    return analyze_python_code(
        file, python_version, encoding, functions_to_analyze, ignore
    )


# WARNING: This endpoint can pose a security risk if exposed to the public.
@app.post("/analyse_directory/")
async def analyse_directory(
    directory_path: str,
    python_version: tuple = Depends(validate_python_version),
    encoding: str = Depends(validate_encoding),
    functions_to_analyze: Optional[str] = None,
    ignore: Optional[str] = None,
):
    """Analyse all Python files in a directory and return their structures."""

    # Ensure the directory is a subdirectory of the base directory
    if not directory_path.startswith(BASE_DIRECTORY):
        logger.error(
            f"Invalid directory path: {directory_path}. Not within the allowed base directory."
        )
        raise HTTPException(status_code=400, detail="Invalid directory path.")

    # Ensure the directory path does not use relative references
    if ".." in directory_path:
        logger.error(
            f"Invalid directory path: {directory_path}. Relative directory references are not allowed."
        )
        raise HTTPException(status_code=400, detail="Invalid directory path.")

    if not os.path.exists(directory_path) or not os.path.isdir(directory_path):
        raise HTTPException(status_code=400, detail="Invalid directory_path")

    results = {}
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()
                except Exception as e:
                    results[file_path] = f"Error reading file: {str(e)}"
                    continue

                try:
                    result = analyze_python_code(
                        file_bytes,
                        python_version,
                        encoding,
                        functions_to_analyze,
                        ignore,
                    )
                except Exception as e:
                    results[file_path] = f"Error during analysis: {str(e)}"
                    continue

                results[file_path] = result

    return results
