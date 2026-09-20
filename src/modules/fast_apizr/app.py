from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from .configuration import FastApizrConfiguration
from .generator.analyzr import Analyzr
from .generator.fastApiAppGenerator import FastApiAppGenerator

app = FastAPI(title="Fast Apizr")


@app.post("/get_fastapi_code/", response_class=PlainTextResponse)
def create_file(conf: FastApizrConfiguration, analyse: Analyzr):
    try:
        return FastApiAppGenerator(conf, analyse).gen_fastapi_app()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
