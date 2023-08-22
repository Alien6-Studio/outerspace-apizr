---
title: Analyzing Python codebase to extract API endpoints 
description: Code Analyzr extracts API endpoints from Python codebase and generates a configuration file for Apizr.
---

## API Endpoints

Code Analyzr provides the following API endpoints:

### POST /analyse_file

Analyzes a Python file and returns its structure.

#### Parameters

- `python_version` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
- `encoding` (string, optional): The encoding of the file. Defaults to "utf-8".
- `file` (bytes, required): The file to analyze.

#### Returns

A dictionary with the analysis result.

### POST /analyse_directory

Analyzes all Python files in a directory and returns their structures.

#### Parameters

- `directory_path` (string, required): The path of the directory to analyze.
- `python_version` (string, optional): The Python version to use for the analysis. Defaults to "3.8".
- `encoding` (string, optional): The encoding of the files. Defaults to "utf-8".

#### Returns

A dictionary where the keys are file paths and the values are analysis results.

