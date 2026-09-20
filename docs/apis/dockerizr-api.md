---
title: Automating Dockerization of Python Projects
description: Dockerizr provides API endpoints to facilitate the dockerization of Python projects.
---

**Description**: Dockerizr provides the following API endpoints to assist in generating various files for containerization.

## API Endpoints

!!! info "POST /generate_gunicorn_files/"

    Generates files required for Gunicorn.

    **Parameters**:

    - `conf` (DockerizrConfiguration): The configuration details for generating Gunicorn files.

    **Returns**:

    A success message indicating that Gunicorn files were generated successfully.

!!! info "POST /generate_requirements/"

    Generates a `requirements.txt` file based on the provided configuration.

    **Parameters**:

    - `conf` (DockerizrConfiguration): The configuration details for generating the `requirements.txt` file.

    **Returns**:

    A success message indicating that the `requirements.txt` file was generated successfully.

!!! info "POST /generate_dockerfile/"

    Generates a Dockerfile based on the provided configuration.

    **Parameters**:

    - `conf` (DockerizrConfiguration): The configuration details for generating the Dockerfile.

    **Returns**:

    A success message indicating that the Dockerfile was generated successfully.

## Models

### GunicornConfiguration

!!! abstract "GunicornConfiguration"

    Defines the configuration for the server that will run the application.

    - `server_app` (str): Server application name. Defaults to "gunicorn".
    - `wsgi_file_name` (str): Name of the WSGI file. Defaults to "wsgi.py".
    - `wsgi_conf_file_name` (str): Name of the WSGI configuration file. Defaults to "gunicorn.conf.py".
    - `host` (str): Host address for the server. Defaults to "0.0.0.0".
    - `port` (int): Port number for the server. Defaults to 5001.
    - `workers` (int): Number of workers for the server. Defaults to 2.
    - `timeout` (int): Timeout in seconds. Defaults to 60.

### DockerizrConfiguration

!!! abstract "DockerizrConfiguration"

    Configuration settings for the Dockerizr module. Provides settings related to the Docker containerization of the application.

    - `python_version` (tuple): The Python version to be used. Defaults to (3, 8).
    - `encoding` (str): The character encoding format for reading and writing files. Defaults to "utf-8".
    - `docker_image` (str): Docker image name. Defaults to "alpine".
    - `docker_image_tag` (str): Docker image tag. Defaults to "alpine3.18".
    - `dependencies` (List[Dependency]): List of dependencies and associated packages.
    - `custom_packages` (List[str]): List of custom packages.
    - `project_path` (str): Path to the project directory. Defaults to the current directory.
    - `main_folder` (Optional[str]): Name of the main folder for the project.
    - `api_filename` (str): Name of the generated FastAPI application file. Defaults to "app.py".
    - `server` (GunicornConfiguration): Configuration settings for the Gunicorn server.
    - `apizr_requirements` (List[str]): List of required packages for Apizr.

More information about the Dockerizr module can be found [here](/modules/dockerizr/).
