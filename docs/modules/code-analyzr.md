---
title: Analyzing Python codebase to extract API endpoints 
description: Code Analyzr extracts API endpoints from Python codebase and generates a configuration file for Apizr.
---

[![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-380/)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-31012/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3114/)

## Overview

The code-analyzr project is designed to extract API endpoints from a provided Python codebase through AST (Abstract Syntax Tree) parsing. The primary entry point is the `app.py` file, offering functionalities for input validation, code analysis, and file creation.

The heart of the extraction process is the `AstAnalyzr` class located in the `analyzr/astAnalyzr.py` file. This class uses Python's built-in `ast` module to parse the provided code and derive meaningful information. The project is further supported by multiple helper classes within the `analyzr/ast_node/` directory, each dedicated to handling a specific type of AST node, such as annotations, functions, and imports.

## Project Structure

The codebase structure involves:

- **app.py**: Serves as the main entry point. It encompasses functionalities for input validation, code analysis, and file handling.
- **analyzr/astAnalyzr.py**: Contains the core `AstAnalyzr` class, which performs the main analysis.
- **analyzr/ast_node/**: A directory that houses helper classes, each tailored to process and derive information from their respective AST nodes.

## Libraries and Tools

The project leans heavily on Python's built-in `ast` module for parsing. It also incorporates other built-in libraries like `os` for file operations, `json` for JSON serialization/deserialization, and `re` for regular expression operations. The `typing` module facilitates type annotations, granting clarity and type-checking for function arguments and returns.

## Usage

For utilizing the `AstAnalyzr` class:

```python
from analyzr import AstAnalyzr
```

You can then use the `AstAnalyzr` class to analyze your Python code:

```python
analyzer = AstAnalyzr(your_python_code, version=(3, 8))
result = analyzer.get_analyse()
```

This will return a JSON string with the analysis result of the provided Python code.

### Docker

To use the Code Analyzr module as a Docker container, you'll need to have Docker installed on your system. Once you've confirmed that Docker is installed, you can pull the Code Analyzr image from Docker Hub as follows:

```bash
docker pull outerspace.alien6.com/code-analyzr
```

You can then run the Code Analyzr container as follows:

```bash
docker run -it --rm outerspace.alien6.com/code-analyzr
```

---

### Usecase

When you provide Python source code to `CodeAnalyzr`, it scans the code to identify:

- Compatible Python versions
- Functions present in the code, their arguments, annotations, default values, and return values
- Imported modules

The output is a structured JSON object that can be used directly or supplied to other tools for further use.

#### Example

Take a simple example:

```python
import math

def add(a: int, b: int) -> int:
    return a + b
```

The output from `CodeAnalyzr` would be:

```json
{
  "version": [3, 9],
  "functions_to_analyze": [],
  "ignore": [],
  "imports": [{"name": "math", "asname": null}],
  "functions": [
    {
      "name": "add",
      "args": [
        {"name": "a", "annotation": {"type": "int", "of": []}},
        {"name": "b", "annotation": {"type": "int", "of": []}}
      ],
      "returns": {"type": "int", "of": []}
    }
  ]
}
```
