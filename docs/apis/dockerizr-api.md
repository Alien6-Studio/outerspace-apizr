---
title: Automating Dockerization of Python Projects
description: Dockerizr provides API endpoints to facilitate the dockerization of Python projects.
---

## API Endpoints

Dockerizr offers the following API endpoints:

### POST /generate_dockerfile

Automates the creation of a Dockerfile for a specific Python project.

#### Parameters <!-- markdownlint-disable MD024 -->

- `project_path` (string, required): The path to the Python project.
- `base_image` (string, optional): The base Docker image for the Dockerfile. Defaults to "python:3.8".
- `requirements_file` (string, optional): The path to the requirements.txt file. If not provided, Dockerizr will search for it.

#### Returns

A string containing the generated Dockerfile content.

### POST /generate_gunicorn_files/

Generates files for Gunicorn.

#### Parameters

- `configuration` (string, optional): The configuration for Gunicorn.
- `project_path` (string, required): The path to the Python project.

#### Returns

A success message upon successful generation of Gunicorn files.

---

### POST /generate_requirements/

Analyzes and generates a requirements.txt file for a Python project.

#### Parameters

- `project_path` (string, required): The path to the Python project.

#### Returns

A string containing the generated requirements.txt content.
