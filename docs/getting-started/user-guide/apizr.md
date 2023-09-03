---
title:
description:
---

<!-- markdownlint-disable MD025 -->

APIzr provides a command-line interface (CLI) to convert Jupyter notebooks or Python scripts into containers, analyze Python code, and generate FastAPI applications. This section of the documentation will guide you through the various functionalities and how to use APIzr and its modules effectively.

By default:

- Using the `--notebook` option triggers the "notebook transformr", initiating the process with a Jupyter notebook as the input.
- The `--script` option starts from the next phase, analyzing a given Python script.

It's important to note that the `--script` and `--notebook` options are mutually exclusive, meaning you can only use one at a time.

For users who want more control over specific steps:

- The `--skip-docker` option skips the containerization phase.
- The `--skip-pipreqs` option omits the generation of the `pipreqs` file, allowing users to manually specify package versions if desired.

## Configuration Details

The execution can be tailored using a configuration file. The configuration is segmented into different sections, each catering to a specific module or general setting. Users can create their own configuration file based on provided templates or detailed instructions, allowing for a customized experience:

- **General Settings**: Define the Python version and file encoding.
- **CodeAnalyzr**: Configure the Python script path, functions to analyze, functions to ignore, and specific keywords for certain Python versions.
- **FastAPIzr**: Specify the module name and the name of the generated file.
- **Dockerizr**: Customize Docker settings, including the Docker image, dependencies, custom packages, and server configurations.

If neither the `--configuration` option nor the `--force` option is specified, the CLI will, by default, prompt the user to configure the execution interactively. However, you can:

- Directly specify a configuration file using the `--configuration` option.
- Use the `--force` option to execute with default settings, bypassing interactive prompts.
