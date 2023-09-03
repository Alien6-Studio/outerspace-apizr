---
title: Processing and Dockerizing Python Code
description: Apizr processes Python and Jupyter Notebook files and offers dockerization capabilities.
---

**Description**: Apizr is designed to process and dockerize Python and Jupyter Notebook files. It provides endpoints for converting Jupyter Notebooks into Python code, processing code, and dockerizing Python applications.

## API Endpoints

!!! info "POST /process_file/"

    Converts Jupyter Notebook files into Python code, processes the code, and returns the structured output path.

    **Parameters**:

    - `file` (UploadFile, required): The file to process. It can be a Python file or a Jupyter Notebook.
    - `output` (string, optional): Path where the processed file should be saved.

    **Returns**:

    A dictionary with:
    - `status` (string): Returns "success" if the processing is successful.
    - `output_path` (string): The path to the processed file.

    **Errors**:

    - Returns a `400 Bad Request` error if the file type is invalid.
    - Returns a `500 Internal Server Error` for other exceptions during processing.

!!! info "POST /dockerize_file/"

    Dockerizes the given file.

    **Parameters**:

    - `filename` (string, required): Name of the file to be dockerized.
    - `output` (string, required): Path where the dockerized file should be saved.

    **Returns**:

    A dictionary with:
    - `status` (string): Returns "success" if dockerization is successful.

    **Errors**:

    - Returns a `400 Bad Request` if the filename is empty.
    - Returns a `500 Internal Server Error` for other exceptions during dockerization.
