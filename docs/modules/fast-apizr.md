---
title: Generating FastAPI Endpoints from Python Code Analysis
description: FastApizr uses the output from Code Analyzr to generate FastAPI endpoints for a given Python codebase.
---

[![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-380/)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-31012/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3114/)

## Overview

FastApizr is a tool designed to generate FastAPI endpoints by leveraging the output from the Code Analyzr project. The main goal is to automate the process of API creation based on Python codebase analysis. Given the structured output from Code Analyzr, FastApizr can efficiently produce corresponding FastAPI routes, facilitating rapid API development.

## Project Structure

The main components of the FastApizr codebase include:

- **app.py**: This file serves as the central entry point. It contains functionalities for handling input, generating API routes, and saving the resultant FastAPI code.
- **generators/**: A directory that holds classes responsible for creating FastAPI routes based on the information from Code Analyzr's output.

## Libraries and Tools

FastApizr heavily relies on the FastAPI framework to generate API routes. It also employs Python's built-in `json` module for handling JSON data and uses the `typing` module to ensure proper type annotations throughout the code.

## Usage

To use FastApizr, start by importing the main class:

```python
from fastapizr import FastApizr
```

Then, provide the JSON output from Code Analyzr to generate FastAPI routes:

```python
generator = FastApizr(json_output_from_code_analyzr)
fastapi_code = generator.generate_api()
```

The result is a FastAPI code with routes corresponding to the functions detected in the initial Python codebase.

### Docker

To use FastApizr as a Docker container, ensure Docker is installed on your system. Afterward, you can pull the FastApizr image from Docker Hub:

```bash
docker pull outerspace.alien6.com/fastapizr
```

To run the FastApizr container, execute:

```bash
docker run -it --rm outerspace.alien6.com/fastapizr
```

---

### Usecase

FastApizr's primary use case is to expedite the process of creating APIs from existing Python code. By analyzing the Python code with Code Analyzr and using the resultant JSON output, FastApizr crafts FastAPI routes that mirror the detected functions in the original code.

#### Example

Given an analyzed output from Code Analyzr:

```json
{
  "version": [3, 9],
  "functions_to_analyze": [],
  "ignore": [],
  "imports": [{"name": "math", "asname": null}],
  "imports_from": [],
  "functions": [
    {
      "name": "add",
      "args": [
        {"name": "a", "annotation": {"type": "int", "of": []}},
        {"name": "b", "annotation": {"type": "int", "of": []}}
      ],
      "returns": {"type": "int", "of": []},
      "selected": true
    }
  ]
}
```

FastApizr will produce a FastAPI route similar to:

```python
from fastapi import FastAPI
from pydantic import BaseModel

import main as main

app = FastAPI()

class Add_model(BaseModel):
   a: int
   b: int

@app.post('/add')
def add_service( arguments: Add_model):  
    try:
        return main.add(a = arguments.a, b = arguments.b)
    except Exception as err:
      return {"errors": "an exception was thrown during program execution"}, 500
```
