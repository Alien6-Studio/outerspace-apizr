# Standard library imports
import logging
import os
from pathlib import Path

# Third party imports
from fastapi import FastAPI, File, HTTPException, UploadFile, Query
from typing import Optional

# Local application imports
import main
from exceptions import (
    InvalidFileExtensionError,
    InvalidNotebookError,
    InvalidScriptError,
    MetadataGenerationError,
    FastApiGenerationError,
)

# Setup the logger configuration
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)
logger = logging.getLogger(__name__)

# Create a FastAPI application instance
app = FastAPI()


def extract_code_from_file(file: UploadFile, output) -> tuple:
    """
    Extracts Python code from the given file based on its extension.
    """

    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    file_name = file.filename
    file_extension = os.path.splitext(file_name)[1]
    file_content = file.file.read()

    if file_extension == ".ipynb":
        # Save the notebook content temporarily
        temp_notebook_path = Path.cwd() / file_name
        with temp_notebook_path.open("wb") as temp:
            temp.write(file_content)

        # Convert the notebook to code
        code, script_name = main.convert_notebook_to_code(temp_notebook_path, output)

        # Clean up the temporary notebook file
        temp_notebook_path.unlink()

        return code, script_name
    elif file_extension == ".py":
        return file_content.decode(), ""
    else:
        raise ValueError("Unsupported file type")


def process_and_save_code(code: str, filename: str, output: Optional[str]) -> Path:
    """Process the given code, save it to a temporary file, and call main.process_input."""
    temp_file_path = (
        Path.cwd() / filename
    )  # Save with the original filename in the current directory

    with temp_file_path.open("w", encoding="utf-8") as temp:
        temp.write(code)

    output_path = Path(output) if output else Path.cwd()
    output_path.mkdir(parents=True, exist_ok=True)

    main.process_input(temp_file_path, output_path)

    temp_file_path.unlink()  # Clean up the temporary file
    return output_path


@app.post("/process_file/")
async def process_file(file: UploadFile = File(...), output: Optional[str] = None):
    """Process a file and return its structured output."""

    try:
        filename = file.filename
        code, filename = extract_code_from_file(file, output)
        processed_output_path = process_and_save_code(code, filename, output)
        return {"status": "success", "output_path": str(processed_output_path)}
    except InvalidFileExtensionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dockerize_file/")
async def dockerize_file(
    filename: str = Query(..., description="Name of the file to be dockerized."),
    output: str = Query(
        ..., description="Path where the dockerized file should be saved."
    ),
):
    """Dockerize the given file."""
    if not filename:
        raise HTTPException(status_code=400, detail="Filename cannot be empty")

    try:
        main.dockerize_app(
            script_name=filename, output=Path(output)
        )  # Convert output to Path
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error dockerizing file: {e}")
        raise HTTPException(status_code=500, detail=str(e))
