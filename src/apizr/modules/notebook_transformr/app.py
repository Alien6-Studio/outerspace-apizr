import io

from fastapi import FastAPI, File, HTTPException, UploadFile

from apizr.http import read_upload

from .transformr import NotebookTransformr

app = FastAPI(title="Notebook Transformr")


@app.post("/convert_notebook")
def convert_notebook(file: UploadFile = File(...)):
    _, content = read_upload(file, {".ipynb"})
    try:
        source, _ = NotebookTransformr().convert_notebook(
            io.StringIO(content.decode("utf-8"))
        )
        return {"script": source}
    except (ValueError, SyntaxError, UnicodeError) as exc:
        raise HTTPException(400, str(exc)) from exc
