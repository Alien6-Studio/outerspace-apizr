"""REST mapping for the shared governed executor. Direct REST is separate."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from apizr.execution.protocol import finite_json
from apizr.repository_interfaces.runtime import read_artifact as artifact

from .runtime import GovernedRuntime


def create_app(root: Path) -> FastAPI:
    runtime = GovernedRuntime(root, "rest")
    document = json.loads(artifact(root, "openapi.json"))
    app = FastAPI(title="Apizr REST API", docs_url="/docs", redoc_url=None)
    app.openapi = lambda: document
    app.state.apizr = runtime

    @app.get("/health", response_model=None)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    def handler(capability: str) -> Callable[[Request], Awaitable[JSONResponse]]:
        async def invoke(request: Request) -> JSONResponse:
            try:
                payload = finite_json(await request.json())
            except (ValueError, UnicodeError, RecursionError):
                raise HTTPException(422, "Invalid request arguments") from None
            result = await run_in_threadpool(runtime.invoke, capability, payload)
            if result.status == "success":
                return JSONResponse(content=result.value)
            if result.status == "invalid_input":
                raise HTTPException(422, "Invalid request arguments")
            if result.status == "timeout":
                raise HTTPException(504, "Execution timed out")
            if result.status == "resource_limit":
                raise HTTPException(503, "Execution resource limit exceeded")
            raise HTTPException(500, "Internal server error")

        return invoke

    for capability in runtime.contract.capabilities:
        app.add_api_route(
            "/capabilities/" + capability.public_name,
            handler(capability.capability_id),
            methods=["POST"],
            response_model=None,
            operation_id=capability.capability_id,
        )
    return app
