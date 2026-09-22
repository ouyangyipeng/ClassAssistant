import hashlib
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile

from classfox.audio import AudioError, decode_wav
from classfox.models import TranscriptEntry
from classfox.runtime import Classroom
from classfox.speech import SpeechService


def audio_routes() -> APIRouter:
    router = APIRouter(prefix="/api/v2")

    @router.get("/audio/devices")
    async def devices(request: Request) -> list[dict[str, object]]:
        speech: SpeechService = request.app.state.speech
        return await speech.devices()

    @router.post("/sessions/{session_id}/audio")
    async def upload(
        request: Request,
        session_id: str,
        file: Annotated[UploadFile, File()],
        source_id: Annotated[str, Form(min_length=1, max_length=128)],
    ) -> dict[str, TranscriptEntry | bool | None]:
        classroom: Classroom = request.app.state.classroom
        speech: SpeechService = request.app.state.speech
        try:
            data = await file.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise AudioError("音频片段不能超过 1 MiB，请分段上传")
            pcm = decode_wav(data)
        finally:
            await file.close()
        digest = hashlib.sha256(pcm).hexdigest()
        async with classroom.audio_upload_lock:
            session = classroom.store.get_session(session_id, owner_id="desktop")
            found, previous = classroom.store.audio_receipt(session_id, source_id, digest)
            if found:
                return {"entry": previous, "duplicate": True}
            if classroom.active_id != session_id or session.status != "recording":
                raise ValueError("请先开始或恢复此课堂，再上传音频")
            text = await speech.transcribe(pcm)
            if classroom.active_id != session_id:
                raise ValueError("此课堂已结束，识别结果未写入其他课堂")
            entry, created = classroom.store.accept_audio(session_id, source_id, digest, text)
            if created and entry is not None:
                classroom.publish_entry(session, entry)
            return {"entry": entry, "duplicate": not created}

    return router
