---
title: Converting Jupyter notebooks to Python scripts
description: Notebook Transformr converts Jupyter notebooks to Python scripts, optimizing the output and generating dependencies.
---

[![Python 3.8](https://img.shields.io/badge/python-3.8-blue.svg)](https://www.python.org/downloads/release/python-380/)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/release/python-390/)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-31012/)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3114/)

## Introduction

The Notebook Transformr module, part of OuterSpace Apizr, is a Python utility that leverages `nbconvert` to transform Jupyter notebooks (.ipynb files) into Python modules (.py files). It includes additional features like removing consecutive empty lines, filtering specific lines, and leveraging pipreqs to generate a `requirements.txt` file with notebook dependencies. It's compatible with Python 3.8 and later versions.

---

## Features

- **Conversion to Python**: Converts Jupyter notebooks to Python scripts.
- **Line Filtering**: Removes unnecessary lines like the shebang and `# In[X]`.
- **Empty Line Compression**: Reduces consecutive empty lines to a single empty line.
- **Code Formatting with Black**: Utilizes the Black code formatter to ensure that the generated code is clean and consistent with the PEP 8 style guide.
- **Requirements Generation**: Generates a `requirements.txt` file based on the notebook's dependencies.

---

## Usage

### Installation

To use `Notebook Transformr`, install the required dependencies using the `requirements.txt` file located in the `apizr/src/notebook_transformr` directory.

```bash
pip install -r requirements.txt
```

### Codebase

To convert a Jupyter notebook into a Python module, use the `NotebookTransformr` class from the `notebook_transformr` module.

```python
from notebook_transformr import NotebookTransformr

transformer = NotebookTransformr()
source, _ = transformer.convert_notebook(file_path)
output_path = transformer.save_script(source, output_dir, filename)
```

This will generate a `.py` file in the specified output directory and handle specific formatting options like removing consecutive empty lines.

### Docker

To use Notebook Transformr as a Docker container, you'll need Docker installed on your system. Pull the Notebook Transformr image from Docker Hub:

```bash
docker pull outerspace.alien6.com/notebook-transformr
```

Run the Notebook Transformr container:

```bash
docker run -it --rm outerspace.alien6.com/notebook-transformr
```
