"""REST mapping for the shared governed executor. Direct REST is separate."""

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from apizr.execution.protocol import finite_json

from .runtime import GovernedRuntime, artifact


def create_app(root: Path) -> FastAPI:
    runtime = GovernedRuntime(root, "rest")
    document = json.loads(artifact(root, "openapi.json"))
    app = FastAPI(title="Apizr REST API", docs_url="/docs", redoc_url=None)
    app.openapi = lambda: document

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
            raise HTTPException(500, "Internal server error")

        return invoke

    for capability, plan in runtime.plans.items():
        app.add_api_route(
            "/capabilities/" + plan.interface.name,
            handler(capability),
            methods=["POST"],
            response_model=None,
            operation_id=capability,
        )
    return app
