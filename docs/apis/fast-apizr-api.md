---
title: Generating FastAPI Code from Analysis
description: Fast Apizr creates FastAPI code based on provided configuration and analysis.
---

**Description**: Fast Apizr creates FastAPI code based on provided configuration and analysis.

## API Endpoints

!!! info "POST /get_fastapi_code/"

    Generates FastAPI code based on the provided configuration and analysis.

    **Parameters**:

    - `conf` (FastApizrConfiguration): The configuration details for the FastAPI code generation.
    - `analyse` (Analyzr): The analysis details to guide the code generation.

    **Returns**:

    The generated FastAPI code as a plain text response.

## Model: FastApizrConfiguration

Fast Apizr uses the `FastApizrConfiguration` model to define the configuration details for generating the FastAPI application. The model has the following attributes:

!!! abstract "Attributes"

    - `python_version` (tuple): Represents the Python version to be used. It's a tuple containing two integers that represent the major and minor version respectively. Defaults to `(3, 8)`, which corresponds to Python 3.8.
    - `encoding` (str): The character encoding format used for reading and writing files. Defaults to `"utf-8"`.
    - `module_name` (str): The name of the module for the generated application. Defaults to `"main"`.
    - `api_filename` (str): The name of the generated FastAPI application file. Defaults to `"app.py"`.

More information about the Fast Apizr module can be found [here](/modules/fast-apizr/).
