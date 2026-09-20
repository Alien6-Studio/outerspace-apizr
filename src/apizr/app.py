"""Local generation API. Uploaded code is never executed by the generator."""

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from apizr.modules.code_analyzr.analyzr.ast_node.astNodeException import (
    AnnotationException,
)

from .http import read_upload
from .main import convert
from .modules.code_analyzr.app import app as code_app
from .modules.dockerizr.app import app as docker_app
from .modules.fast_apizr.app import app as fastapi_app
from .modules.notebook_transformr.app import app as notebook_app

app = FastAPI(title="OuterSpace Apizr", version="0.2.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/process_file/")
def process_file(file: UploadFile = File(...)):
    """Return a ZIP project; server-side output paths are intentionally not accepted."""
    filename, content = read_upload(file, {".py", ".ipynb"})
    temporary = TemporaryDirectory(prefix="apizr-")
    try:
        root = Path(temporary.name)
        source = root / filename
        source.write_bytes(content)
        output = root / "project"
        convert(source, output)
        archive = root / "project.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
            for path in output.rglob("*"):
                if path.is_file():
                    bundle.write(path, path.relative_to(output))
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"{source.stem}-api.zip",
            background=BackgroundTask(temporary.cleanup),
        )
    except (ValueError, SyntaxError, UnicodeError, AnnotationException) as exc:
        temporary.cleanup()
        raise HTTPException(400, str(exc)) from exc
    except Exception:
        temporary.cleanup()
        raise


app.mount("/code", code_app)
app.mount("/fastapi", fastapi_app)
app.mount("/docker", docker_app)
app.mount("/notebook", notebook_app)
