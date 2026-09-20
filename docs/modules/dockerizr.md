# Dockerizr

Dockerizr generates a Dockerfile, Uvicorn startup script and `.dockerignore`. The complete pipeline uses `python:<target>-slim`, where the target defaults to the running interpreter (3.8–3.14), runs as UID 10001, and checks `/health` on port 5001. Alpine templates are also available; their image tag must begin with `alpine`.

Dependencies are inferred statically from imports, excluding standard-library and local modules. Installed distribution versions are pinned when available. Supply an explicit requirements file for packages that cannot be inferred reliably. Explicit requirements use PEP 508 syntax.

Configure native dependencies through `dockerizr.dependencies` (distribution name → system packages) and `dockerizr.custom_packages`. Choose package names appropriate to Debian or Alpine. Native packages are installed before Python dependencies.

The optional legacy Gunicorn generator remains accessible for existing integrations; its worker class is `uvicorn_worker.UvicornWorker` and requires `gunicorn` and `uvicorn-worker` in the consuming environment. The main pipeline uses Uvicorn directly and needs neither package.
