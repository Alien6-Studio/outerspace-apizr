---
title: Converting Jupyter notebooks to Python scripts
description: Notebook Transformr converts Jupyter notebooks to Python scripts.
---

## API Endpoints

Code Analyzr provides the following API endpoints:

### POST /convert_notebook

#### Parameters

- `python_version` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
- `encoding` (string, optional): The encoding of the file. Defaults to "utf-8".
- `output_directory` (string, optional): The directory to save the converted Python script. Defaults to None.
- `file` (bytes, required): The notebook file to convert.

#### Returns

A dictionary containing the Python script as a string, or a success message if the `output_directory` parameter is provided.
