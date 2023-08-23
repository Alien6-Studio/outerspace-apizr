import os

from fastapi import FastAPI, UploadFile, File, HTTPException
from transformr import NotebookTransformr

app = FastAPI()

@app.post("/convert_notebook")
async def convert_notebook(
    python_version: str = "3.8",
    encoding: str = "utf-8",
    output_directory: str = None,
    file: UploadFile = File(...),
):
    """
    Converts a Jupyter notebook to a Python script.

    Args:
        ...
    """

    # Validate the file extension
    if not file.filename.endswith(".ipynb"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a .ipynb file.",
        )

    transformer = NotebookTransformr(python_version, encoding)

    try:
        # Read the file
        content = await transformer.read_file(file)

        # Convert the notebook to a Python script
        source, _ = transformer.convert_notebook(content)

        # If an output directory is provided, save the script there
        if output_directory:
            output_path = transformer.save_script(
                source, output_directory, file.filename
            )
            return {"message": f"Script successfully saved to {output_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"script": source}
