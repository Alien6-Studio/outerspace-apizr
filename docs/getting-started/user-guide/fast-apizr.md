---
title:
description:
---

# Using FastAPIzr <!-- markdownlint-disable MD025 -->

FastAPIzr serves as a bridge between the analysis of your Python code and the generation of FastAPI applications. After using CodeAnalyzr to analyze a Python script, FastAPIzr takes the resulting output and transforms it into a fully-fledged FastAPI application.

## Basic Usage

To generate a FastAPI application using the output from CodeAnalyzr:

```bash
python fast-apizr/main.py --file [OUTPUT_FROM_CODEANALYZR]
```

Ensure you provide the appropriate output from CodeAnalyzr, as FastAPIzr relies on this specific format to generate the FastAPI application.

## Advanced Configuration

To tailor the generation process to your needs, several options are at your disposal:

- `--version [PYTHON_VERSION]`: Designate the Python version for the application generation.
- `--encoding [ENCODING]`: Determine the file encoding.
- `--module_name [MODULE_NAME]`: Define the name of the module.
- `--api_filename [FILENAME]`: Specify the name of the generated file. The default filename is `app.py`.
- `--output [OUTPUT_PATH]`: Indicate a path to store the generated FastAPI application.

## Interactive Mode

In the absence of the `--configuration` or `--force` options, FastAPIzr will default to an interactive prompt. This guide assists users in the configuration phase, ensuring that all the required parameters are in place before initiating the generation process.

To bypass the interactive mode and use default settings:

```bash
python fast-apizr/main.py --file [OUTPUT_FROM_CODEANALYZR] --force
```
