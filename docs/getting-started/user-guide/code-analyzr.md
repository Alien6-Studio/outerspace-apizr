---
title:
description:
---

# Using CodeAnalyzr <!-- markdownlint-disable MD025 -->

You may want to analyze Python code using the CodeAnalyzr module without the need to generate a FastAPI application.

```bash
python code_analyzr/main.py --file [PATH_TO_PYTHON_FILE]
```

## Advanced Configuration

For a more tailored experience, various options can be used:

- `--version [PYTHON_VERSION]`: Specify the Python version to use for the analysis.
- `--encoding [ENCODING]`: Define the file encoding.
- `--analyze [FUNCTION_NAMES]`: Provide a comma-separated list of specific functions to analyze. This is useful when you're interested in understanding specific parts of a larger script.
- `--ignore [FUNCTION_NAMES]`: Provide a comma-separated list of functions to ignore during the analysis. This is beneficial if certain functions are already understood or are not relevant to the current analysis scope.
- `--output [OUTPUT_PATH]`: Specify a path to save the analysis result. By default, the result will be displayed in the terminal.

## Interactive Mode

If neither the `--configuration` option nor the `--force` option is provided, CodeAnalyzr will, by default, launch an interactive prompt. This prompt will guide users through the configuration process, ensuring that all necessary parameters are set before the analysis begins.

For users who wish to skip this interactive mode and use default settings, the `--force` option can be used:

```bash
python code_analyzr/main.py --file [PATH_TO_PYTHON_FILE] --force
```
