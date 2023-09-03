---
title:
description:
---

# Setting up your workstation for APIzr <!-- markdownlint-disable MD025 -->

This guide provides you with step-by-step instructions to set up a local development environment for the APIzr project. Follow the steps below to ensure a smooth setup.

## Prerequisites

- Git
- Python (Version as specified in the project's `pyproject.toml` file, 3.10 is recommended)
- Poetry (Python packaging and dependency management tool)

## Installation Steps

### 1. Clone the Repository

First, clone the APIzr repository to your local machine:

```bash
git clone https://github.com/Alien6-Studio/outerspace-apizr.git
cd outerspace-apizr
```

### 2. Install Poetry

If you don't already have Poetry installed, you can install it using the provided command:

```bash
curl -sSL https://install.python-poetry.org | python -
```

For alternative installation methods or further details, refer to the [Poetry documentation](https://python-poetry.org/docs/){target=\_blank}.

### 3. Install Project Dependencies

Once you have Poetry installed and you're inside the project's directory, install the project's dependencies:

```bash
poetry install
```

### 4. Activating the Virtual Environment

Once dependencies are installed, activate the virtual environment created by Poetry:

```bash
poetry shell
```

Now, you're inside the project's virtual environment and are ready to run any Python or project-specific commands.

### 5. Familiarize Yourself with Available Commands

The `makefile` in the project root provides several helpful commands for development tasks. You can view all available commands by running:

```bash
make help
```

Use these commands to lint, format, check the code, and more.
