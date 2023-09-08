---
title: Analyzing Python codebase to extract API endpoints
description: Code Analyzr extracts API endpoints from Python codebase and generates a configuration file for Apizr.
---

**Description**: Code Analyzr extracts API endpoints from Python codebase and generates a configuration file for Apizr.

## API Endpoints

!!! info "POST /analyze_file/"

    Analyzes a Python file and returns its structure.

    **Parameters**:

    - `python_version` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
    - `encoding` (string, optional): The encoding of the file. Defaults to "utf-8".
    - `functions_to_analyze` (string, optional): Comma-separated list of specific functions to analyze. This is useful when you're interested in understanding specific parts of a larger script.
    - `ignore` (string, optional): Comma-separated list of functions to ignore during the analysis. This is beneficial if certain functions are already understood or are not relevant to the current analysis scope.
    - `file` (bytes, required): The file to analyze.

    **Returns**:

    A dictionary containing the analysis result.

!!! info "POST /analyse_directory/"

    Analyzes all Python files in a directory and returns their structures.

    **Parameters**:

    - `directory_path` (string, required): The path of the directory to analyze.
    - `python_version` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
    - `encoding` (string, optional): The encoding of the files. Defaults to "utf-8".
    - `functions_to_analyze` (string, optional): Comma-separated list of specific functions to analyze. This is useful when analyzing a larger project with multiple files.
    - `ignore` (string, optional): Comma-separated list of functions to ignore during the analysis. This can be helpful to exclude certain functions from the analysis.

    **Returns**:

    A dictionary where the keys are file paths and the values are analysis results.

More information about the Code Analyzr module can be found [here](/modules/code-analyzr/).
