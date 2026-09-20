from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile

from apizr.http import read_upload
from apizr.modules.code_analyzr.analyzr.ast_node.astNodeException import (
    AnnotationException,
)

from .analyzr import AstAnalyzr
from .configuration import CodeAnalyzrConfiguration

app = FastAPI(title="Code Analyzr")


@app.post("/analyze_file/")
def analyze_file(
    file: UploadFile = File(...),
    functions_to_analyze: Optional[str] = None,
    ignore: Optional[str] = None,
):
    import json

    _, content = read_upload(file, {".py"})
    try:
        configuration = CodeAnalyzrConfiguration(
            functions_to_analyze=functions_to_analyze, ignore=ignore
        )
        return json.loads(
            AstAnalyzr(configuration, content.decode("utf-8")).get_analyse()
        )
    except (ValueError, SyntaxError, UnicodeError, AnnotationException) as exc:
        raise HTTPException(400, str(exc)) from exc
