---
title: Converting Jupyter notebooks to Python scripts
description: Notebook Transformr converts Jupyter notebooks to Python scripts.
---

**Description**: Notebook Transformr converts Jupyter notebooks to Python scripts.

## API Endpoints

!!! info "POST /convert_notebook"

    **Parameters**:

    - `python_version` (string, optional): The Python version to use for the conversion. Must match the format `x.x` (e.g., "3.8"). Defaults to "3.8".
    - `encoding` (string, optional): The encoding of the file. Defaults to "utf-8".
    - `file` (UploadFile, required): The notebook file to convert. Must have a `.ipynb` extension.
    - `output` (string, optional): The directory to save the converted Python script. If not provided, the script will be returned in the response.

    **Returns**:

    - If the `output` parameter is provided, a success message with the path to the saved script is returned.
    - Otherwise, a dictionary containing the Python script as a string is returned.

    **Errors**:

    - Returns a `400 Bad Request` error if an invalid file type is uploaded.
    - Returns a `500 Internal Server Error` for other exceptions during the conversion process.

More information about the Notebook Transformr module can be found [here](/modules/notebook-transformr/).
