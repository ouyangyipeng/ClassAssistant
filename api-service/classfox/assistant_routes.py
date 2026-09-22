from fastapi import APIRouter, Request

from classfox.assistant import Assistant, AssistantJob
from classfox.assistant_context import TaskRequest


def assistant_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.post("/sessions/{session_id}/assistant", status_code=202)
    async def start(request: Request, session_id: str, payload: TaskRequest) -> AssistantJob:
        assistant: Assistant = request.app.state.assistant
        return assistant.start(session_id, payload)

    @router.get("/assistant")
    async def list_jobs(request: Request, session_id: str | None = None) -> list[AssistantJob]:
        assistant: Assistant = request.app.state.assistant
        return assistant.list_jobs(session_id=session_id)

    @router.post("/assistant/test")
    async def test_connection(request: Request) -> dict[str, int | str | bool]:
        assistant: Assistant = request.app.state.assistant
        return await assistant.probe()

    @router.get("/assistant/{job_id}")
    async def get(request: Request, job_id: str) -> AssistantJob:
        assistant: Assistant = request.app.state.assistant
        return assistant.get(job_id)

    @router.delete("/assistant/{job_id}")
    async def cancel(request: Request, job_id: str) -> AssistantJob:
        assistant: Assistant = request.app.state.assistant
        return await assistant.cancel(job_id)

    return router
