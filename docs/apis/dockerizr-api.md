# Dockerizr API

`POST /docker/generate_dockerfile/` accepts a JSON body with `conf` (DockerizrConfiguration) and `requirements` (requirements-file text). It returns a mapping of generated filenames to content, including `Dockerfile`, `start.sh` and `.dockerignore`.

`POST /docker/generate_gunicorn_files/` accepts a DockerizrConfiguration and returns legacy Gunicorn configuration text. The main pipeline uses Uvicorn directly.

The service does not write to `conf.project_path`: filesystem generation is isolated in a temporary directory. The former server-directory requirements endpoint is removed.

Alternatively run `uv run uvicorn src.modules.dockerizr.app:app` and use the routes without the `/docker` prefix. See `/docs` for schemas.
