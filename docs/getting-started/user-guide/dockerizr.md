---
title:
description:
---

# Using Dockerizr <!-- markdownlint-disable MD025 -->

Dockerizr is the final piece of the puzzle, seamlessly converting your FastAPI application into a containerized solution. By utilizing Dockerizr, you can ensure that your API is packaged with all the necessary dependencies and is ready for deployment in any environment that supports Docker.

## Basic Usage

To containerize your FastAPI application:

```bash
python dockerizr/main.py --project_path [PATH_TO_FASTAPI_PROJECT]
```

Point to the directory containing your FastAPI application, and Dockerizr will manage the containerization process.

## Advanced Configuration

To further tailor the containerization process, various options are available:

- `--configuration [CONFIG_FILE_PATH]`: Specify a configuration file to customize the Dockerization process.
- `--action [ACTION_NAME]`: Choose a specific action, such as generating Gunicorn files, `requirements.txt`, or a Dockerfile.
- `--version [PYTHON_VERSION]`: Designate the Python version for the container.
- `--encoding [ENCODING]`: Determine the file encoding.
- `--project_path [PROJECT_PATH]`: Indicate the path to the FastAPI project that needs containerization.

## Interactive Mode

When executing Dockerizr without specifying the `--configuration` or `--force` options, you'll be prompted to interactively configure the containerization process. Here's an example of what an interactive session might look like:

```bash
$ python dockerizr/main.py --project_path /path/to/your/fastapi/project

> Which Docker image would you like to use? (default is 'alpine'):
  - alpine
  - debian
  Enter your choice: alpine

> Which Docker image tag would you like? (default is 'latest'):
  - alpine3.17
  - alpine3.18
  - latest
  Enter your choice: latest

> Specify the project path: /path/to/your/fastapi/project
> Specify the main folder (default is '.'): /path/to/main_folder
> Name for the API application file (default is 'app.py'): app_name.py

> Which server application would you like to use? (default is 'gunicorn'): gunicorn
> Name for the WSGI file (default is 'wsgi.py'): wsgi_name.py
> Name for the WSGI configuration file (default is 'gunicorn.conf.py'): gunicorn_config.py
> Host for your application (default is '0.0.0.0'): 0.0.0.0
> Desired port (default is '5001'): 5001
> Number of workers (default is '2'): 2
> Timeout in seconds (default is '60'): 60
```
