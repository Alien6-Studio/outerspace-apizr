"""REST transport adapter using the shared framework-neutral invocation core."""

import json
import logging
import types
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from apizr.interfaces.runtime import (
    JSON,
    RuntimeInvocation,
    SourcePlan,
    arguments,
    load_source,
    verify_binding,
)
from apizr.interfaces.runtime import BindingError as BindingError
from apizr.interfaces.runtime import IntegrityError as IntegrityError


class RuntimeEndpoint(RuntimeInvocation):
    route: str


class RuntimePlan(SourcePlan):
    endpoints: list[RuntimeEndpoint]


LOGGER = logging.getLogger("apizr.rest")


def create_app(root: Path, plan: RuntimePlan) -> FastAPI:
    module = load_source(root, plan)
    bindings = [
        (endpoint, verify_binding(module, endpoint)) for endpoint in plan["endpoints"]
    ]
    document: dict[str, JSON] = json.loads((root / "openapi.json").read_bytes())
    app = FastAPI(title="Apizr REST API", docs_url="/docs", redoc_url=None)
    app.openapi = lambda: document

    @app.get("/health", response_model=None)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def handler(
        endpoint: RuntimeEndpoint, function: types.FunctionType
    ) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def invoke(request: Request) -> JSONResponse:
            try:
                payload = await request.json()
                args, kwargs = arguments(function, endpoint, payload)
            except (ValueError, UnicodeError, RecursionError) as error:
                raise HTTPException(status_code=422, detail=str(error)) from None
            try:
                if endpoint["execution"] == "async":
                    result = await function(*args, **kwargs)
                else:
                    result = await run_in_threadpool(function, *args, **kwargs)
                return JSONResponse(content=jsonable_encoder(result))
            except HTTPException:
                raise
            except Exception:
                LOGGER.exception(
                    "Capability invocation failed: %s", endpoint["capability_id"]
                )
                raise HTTPException(
                    status_code=500, detail="Internal server error"
                ) from None

        return invoke

    for endpoint, function in bindings:
        app.add_api_route(
            endpoint["route"],
            handler(endpoint, function),
            methods=["POST"],
            response_model=None,
            operation_id=endpoint["capability_id"],
        )
    return app
