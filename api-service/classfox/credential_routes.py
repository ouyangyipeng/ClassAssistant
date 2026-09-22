import asyncio
from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from classfox.credentials import CREDENTIAL_NAMES, CredentialName, Credentials, import_legacy_settings
from classfox.runtime import Classroom


class CredentialUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: SecretStr = Field(min_length=1, max_length=8192)


class ConfigImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=4096)


def credential_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.get("/credentials")
    async def configured(request: Request) -> dict[str, bool]:
        credentials: Credentials = request.app.state.credentials
        return {name: bool(await asyncio.to_thread(credentials.get, name)) for name in CREDENTIAL_NAMES}

    @router.put("/credentials/{name}")
    async def save(request: Request, name: CredentialName, payload: CredentialUpdate) -> dict[str, bool]:
        credentials: Credentials = request.app.state.credentials
        await asyncio.to_thread(credentials.set, name, payload.value.get_secret_value())
        return {"configured": True}

    @router.delete("/credentials/{name}")
    async def delete(request: Request, name: CredentialName) -> dict[str, bool]:
        credentials: Credentials = request.app.state.credentials
        await asyncio.to_thread(credentials.set, name, None)
        return {"configured": False}

    @router.post("/import-config")
    async def import_config(request: Request, payload: ConfigImport) -> dict[str, object]:
        credentials: Credentials = request.app.state.credentials
        classroom: Classroom = request.app.state.classroom
        return await asyncio.to_thread(import_legacy_settings, Path(payload.path), classroom.settings, credentials)

    return router
