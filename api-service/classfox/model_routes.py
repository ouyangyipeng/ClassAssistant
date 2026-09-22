from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from pydantic import BaseModel

from classfox.model_catalog import ModelDefinition
from classfox.model_install import Installation, ModelInstaller
from classfox.model_process import ModelEndpoint, OwnedModelProcess


class ModelInfo(BaseModel):
    model: ModelDefinition
    installation: Installation


def model_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2/models")

    @router.get("")
    async def catalog(request: Request) -> list[ModelInfo]:
        installer: ModelInstaller = request.app.state.models
        return [ModelInfo(model=definition, installation=installer.status(model_id)) for model_id, definition in installer.catalog.items()]

    @router.post("/{model_id}/install", status_code=202)
    async def install(request: Request, model_id: str) -> Installation:
        installer: ModelInstaller = request.app.state.models
        return installer.start(model_id)

    @router.get("/runtime")
    async def runtime(request: Request) -> dict[str, object]:
        process: OwnedModelProcess = request.app.state.owned_model
        return {"ready": process.ready}

    @router.post("/{model_id}/start")
    async def start_runtime(request: Request, model_id: str) -> dict[str, object]:
        start: Callable[[str], Awaitable[ModelEndpoint]] = request.app.state.local_model
        endpoint = await start(model_id)
        return {"status": "ready", "model_id": model_id, "context_characters": endpoint.context_characters}

    @router.delete("/{model_id}/install")
    async def cancel(request: Request, model_id: str) -> Installation:
        installer: ModelInstaller = request.app.state.models
        return await installer.cancel(model_id)

    return router
