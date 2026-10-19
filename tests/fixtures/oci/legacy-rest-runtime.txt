"""REST transport over the shared verified repository runtime."""

import json
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from apizr.interfaces.runtime import RuntimeInvocation, arguments
from apizr.repository_interfaces.runtime import load_bundle


def create_app(root: Path, expected: dict[str, str] | None = None) -> FastAPI:
    manifest, bindings, loader, artifacts = load_bundle(root, "rest", expected)
    app = FastAPI(title="Apizr Repository REST API", redoc_url=None)
    app.state.repository_loader = loader
    document = json.loads(artifacts["openapi.json"])
    app.openapi = lambda: document

    @app.get("/health", response_model=None)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def handler(contract: dict[str, Any]) -> Any:
        function = bindings[contract["capability_id"]]

        async def invoke(request: Request) -> JSONResponse:
            try:
                args, kwargs = arguments(
                    function, cast(RuntimeInvocation, contract), await request.json()
                )
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(422, "Invalid request arguments") from None
            try:
                if contract["execution"] == "async":
                    result = await function(*args, **kwargs)
                else:
                    result = await run_in_threadpool(function, *args, **kwargs)
                return JSONResponse(content=jsonable_encoder(result))
            except Exception:
                raise HTTPException(500, "Internal server error") from None

        return invoke

    for contract in manifest["endpoints"]:
        app.add_api_route(
            contract["route"],
            handler(contract),
            methods=["POST"],
            response_model=None,
            operation_id=contract["capability_id"],
        )
    return app
