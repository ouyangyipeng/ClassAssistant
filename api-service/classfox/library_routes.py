import asyncio
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from classfox.config import RuntimeConfig
from classfox.document_process import parse_isolated
from classfox.documents import DocumentError
from classfox.migration import import_legacy_data
from classfox.models import Material, Summary
from classfox.runtime import Classroom


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    directory: str = Field(min_length=1, max_length=4096)


def library_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.get("/materials")
    async def materials(request: Request) -> list[dict[str, object]]:
        classroom: Classroom = request.app.state.classroom
        return [
            {"id": item.id, "filename": item.filename, "characters": len(item.text), "created_at": item.created_at.isoformat()}
            for item in classroom.store.list_materials()
        ]

    @router.post("/materials", status_code=201)
    async def upload(request: Request, file: UploadFile) -> Material:
        config: RuntimeConfig = request.app.state.config
        classroom: Classroom = request.app.state.classroom
        async with request.app.state.parse_gate:
            content = await file.read(config.upload_limit + 1)
            if len(content) > config.upload_limit:
                raise HTTPException(status_code=413, detail="资料超过允许的体积，请拆分后上传")
            filename = (file.filename or "资料").replace("\\", "/").rsplit("/", 1)[-1][:200]
            try:
                text = await parse_isolated(content, filename)
            except DocumentError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return classroom.store.add_material(filename, text)

    @router.get("/sessions/{session_id}/summaries")
    async def summaries(request: Request, session_id: str) -> list[Summary]:
        classroom: Classroom = request.app.state.classroom
        classroom.store.get_session(session_id, owner_id="desktop")
        return classroom.store.list_summaries(session_id)

    @router.get("/summaries/{summary_id}/export")
    async def export_summary(request: Request, summary_id: str) -> PlainTextResponse:
        classroom: Classroom = request.app.state.classroom
        summary = classroom.store.get_summary(summary_id)
        classroom.store.get_session(summary.session_id, owner_id="desktop")
        return PlainTextResponse(summary.markdown, media_type="text/markdown", headers={"Content-Disposition": 'attachment; filename="classroom-notes.md"'})

    @router.post("/import")
    async def import_data(request: Request, payload: ImportRequest) -> dict[str, object]:
        classroom: Classroom = request.app.state.classroom
        result = await asyncio.to_thread(import_legacy_data, Path(payload.directory), classroom.store)
        return asdict(result)

    return router
