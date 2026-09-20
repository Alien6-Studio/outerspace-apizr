from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import Body, FastAPI, HTTPException

from .configuration import DockerizrConfiguration
from .generator import DockerfileGenerator, GunicornGenerator

app = FastAPI(title="Dockerizr")


@app.post("/generate_gunicorn_files/")
def generate_gunicorn_files(conf: DockerizrConfiguration):
    generator = GunicornGenerator(conf)
    return {
        "wsgi.py": generator.gunicorn_wsgi_generator(),
        "gunicorn.conf.py": generator.gunicorn_conf_generator(),
    }


@app.post("/generate_dockerfile/")
def generate_dockerfile(
    conf: DockerizrConfiguration, requirements: str = Body(default="")
):
    try:
        with TemporaryDirectory(prefix="apizr-docker-") as directory:
            config = conf.model_copy(update={"project_path": directory})
            Path(directory, "requirements.txt").write_text(
                requirements, encoding="utf-8"
            )
            DockerfileGenerator(config).generate_dockerfile()
            return {
                p.name: p.read_text(encoding="utf-8")
                for p in Path(directory).iterdir()
                if p.is_file()
            }
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
