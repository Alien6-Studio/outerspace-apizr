import logging
import os
import re
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from transformr import NotebookTransformr

from configuration import NotebookTransformrConfiguration

# Configure logging settings
logging.basicConfig(
    level=logging.ERROR,
    format="%(asctime)s [%(levelname)s]: %(message)s",
    filename="app_errors.log",
)

logger = logging.getLogger(__name__)


app = FastAPI()


@app.post("/convert_notebook")
async def convert_notebook(
    python_version: str = Query("3.8", regex="^\\d+\\.\\d+$"),
    encoding: str = "utf-8",
    file: UploadFile = File(...),
    output: Optional[str] = None,
):
    """
    Converts a Jupyter notebook to a Python script.

    Args:
        ...
    """

    # Validate the file extension
    if file.filename and not file.filename.endswith(".ipynb"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .ipynb file.",
        )

    configuration = NotebookTransformrConfiguration()
    configuration.python_version = tuple(map(int, python_version.split(".")))
    configuration.encoding = encoding
    transformer = NotebookTransformr(configuration=configuration)

    try:
        # Convert the notebook to a Python script
        source, _ = transformer.convert_notebook(file.file)

        if output:
            # If an output directory is provided, save the script there
            output_directory = Path(output)
            output_directory.mkdir(parents=True, exist_ok=True)
            output_path = transformer.save_script(
                source, output_directory, file.filename
            )
            return {"message": f"Script successfully saved to {output_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"script": source}
