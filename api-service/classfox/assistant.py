import asyncio
import logging
import sqlite3
from collections.abc import Callable
from contextlib import aclosing
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import uuid4

from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, Field

from classfox.assistant_context import SYSTEM, TASKS, ContextSnapshot, TaskRequest, answer_messages, summary_chunks
from classfox.credentials import CredentialError
from classfox.events import Event, EventBus
from classfox.llm import LLMError, LLMService
from classfox.settings import LLMSettings, SettingsStore
from classfox.storage import Store

logger = logging.getLogger(__name__)
ACTIVE = {"queued", "running"}


class AssistantJob(BaseModel):
    id: str
    owner_id: str
    session_id: str
    kind: Literal["rescue", "catchup", "summary", "followup"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"] = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    through_entry_id: int
    markdown: str = ""
    stage: str = "等待生成"
    first_token_ms: int | None = None
    total_ms: int | None = None
    provider_calls: int = 0
    summary_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class Assistant:
    def __init__(self, store: Store, settings: SettingsStore, events: EventBus, llm: LLMService) -> None:
        self.store = store
        self.settings = settings
        self.events = events
        self.llm = llm
        self._jobs: dict[str, AssistantJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._probing = False

    def start(
        self, session_id: str, request: TaskRequest, *, owner_id: str = "desktop", local_only: bool = False, guard: Callable[[], None] | None = None
    ) -> AssistantJob:
        if self._probing:
            raise ValueError("正在测试问答服务连接，请稍后生成")
        snapshot = ContextSnapshot.capture(self.store, session_id, owner_id)
        settings = self.llm.context_settings(self.settings.load().llm)
        if local_only and (settings.mode != "local" or not settings.managed):
            raise ValueError("手机连接仅使用电脑已安装的本地问答模型，请先在电脑选择受管本地模型")
        if guard:
            guard()
        active = [job for job in self._jobs.values() if job.status in ACTIVE]
        if len(active) >= 4 or sum(job.owner_id == owner_id for job in active) >= 2:
            raise ValueError("已有生成任务正在进行，请等待完成或取消后重试")
        if any(job.session_id == session_id and job.kind == request.kind for job in active):
            raise ValueError("相同课堂的此类任务已在生成中")
        if request.kind == "summary" and not snapshot.entry_count:
            raise ValueError("课堂还没有原文，暂时无法生成笔记")
        if request.kind != "summary":
            answer_messages(self.store, snapshot, request, settings)
        for job_id, old in list(self._jobs.items()):
            if len(self._jobs) < 100:
                break
            if old.status not in ACTIVE:
                del self._jobs[job_id]
        job = AssistantJob(id=uuid4().hex, owner_id=owner_id, session_id=session_id, kind=request.kind, through_entry_id=snapshot.through_id)
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, snapshot, request, settings, guard), name=f"assistant-{job.id}")
        self._tasks[job.id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(job.id, None))
        return job.model_copy()

    async def probe(self) -> dict[str, int | str | bool]:
        if self._probing or any(job.status in ACTIVE for job in self._jobs.values()):
            raise ValueError("已有问答请求正在进行，请等待完成后测试")
        self._probing = True
        started, first = monotonic(), 0
        settings = self.settings.load().llm.model_copy(update={"timeout_seconds": 30})
        try:
            async with aclosing(self.llm.stream(settings, [{"role": "user", "content": "这是连接测试，请只回复：连接成功。"}], max_tokens=48)) as response:
                async for _text in response:
                    if not first:
                        first = max(1, round((monotonic() - started) * 1000))
            return {
                "ok": True,
                "model": settings.local_model_id if settings.mode == "local" and settings.managed else settings.model,
                "first_token_ms": first,
                "total_ms": round((monotonic() - started) * 1000),
            }
        finally:
            self._probing = False

    def get(self, job_id: str, *, owner_id: str = "desktop") -> AssistantJob:
        job = self._jobs.get(job_id)
        if job is None or job.owner_id != owner_id:
            raise KeyError("未找到生成任务")
        return job.model_copy()

    def list_jobs(self, *, owner_id: str = "desktop", session_id: str | None = None) -> list[AssistantJob]:
        return [job.model_copy() for job in reversed(self._jobs.values()) if job.owner_id == owner_id and (session_id is None or job.session_id == session_id)]

    async def wait(self, job_id: str) -> None:
        if task := self._tasks.get(job_id):
            await asyncio.shield(task)

    async def cancel(self, job_id: str, *, owner_id: str = "desktop") -> AssistantJob:
        self.get(job_id, owner_id=owner_id)
        job = self._jobs[job_id]
        if job.status not in ACTIVE:
            return job.model_copy()
        job.status = "cancelled"
        job.stage = "已取消"
        if task := self._tasks.get(job_id):
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if job.total_ms is None:
            job.total_ms = 0
            self._publish(job, "assistant.finished")
        return job.model_copy()

    async def close(self) -> None:
        for job in list(self._jobs.values()):
            if job.status in ACTIVE:
                await self.cancel(job.id, owner_id=job.owner_id)

    def _publish(self, job: AssistantJob, event_type: str) -> None:
        self.events.publish(job.owner_id, Event(type=event_type, session_id=job.session_id, data=job.model_dump(mode="json")))

    def _progress(self, job: AssistantJob, stage: str) -> None:
        job.stage = stage
        self._publish(job, "assistant.progress")

    async def _run(
        self, job: AssistantJob, snapshot: ContextSnapshot, request: TaskRequest, settings: LLMSettings, guard: Callable[[], None] | None = None
    ) -> None:
        started = monotonic()
        job.status = "running"
        self._progress(job, "等待模型响应")
        try:
            async with asyncio.timeout(1800 if request.kind == "summary" else settings.timeout_seconds):
                if request.kind == "summary":
                    messages = await self._summary_messages(job, snapshot, settings)
                else:
                    messages = answer_messages(self.store, snapshot, request, settings)
                await self._stream_answer(job, messages, settings, started)
                if guard:
                    guard()
                if request.kind == "summary":
                    note = self.store.save_summary(job.session_id, snapshot.session.course_name, job.markdown)
                    job.summary_id = note.id
                job.status = "completed"
                job.stage = "已完成"
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.stage = "已取消"
        except Exception as error:
            self._fail(job, error)
        finally:
            job.total_ms = round((monotonic() - started) * 1000)
            self._publish(job, "assistant.finished")

    @staticmethod
    def _fail(job: AssistantJob, error: Exception) -> None:
        job.status = "failed"
        job.stage = "生成失败"
        if isinstance(error, LLMError):
            job.error_code, job.error_message = error.code, str(error)
        elif isinstance(error, TimeoutError):
            job.error_code, job.error_message = "timeout", "生成已达到时限；原文仍已保留，可以重试"
        elif isinstance(error, CredentialError):
            job.error_code, job.error_message = "credential_store_unavailable", str(error)
        elif isinstance(error, (OSError, sqlite3.Error)):
            job.error_code, job.error_message = "storage_error", "笔记保存失败，请检查磁盘空间；可复制已生成内容后重试"
        else:
            logger.error("Assistant task failed: %s", type(error).__name__)
            job.error_code, job.error_message = "generation_failed", "生成任务出现错误；原文仍已保留，请重试"

    async def _stream_answer(self, job: AssistantJob, messages: list[ChatCompletionMessageParam], settings: LLMSettings, started: float) -> None:
        job.provider_calls += 1
        async with aclosing(self.llm.stream(settings, messages)) as response:
            async for text in response:
                if job.first_token_ms is None:
                    job.first_token_ms = round((monotonic() - started) * 1000)
                offset = len(job.markdown)
                job.markdown += text
                job.stage = "正在生成"
                self.events.publish(
                    job.owner_id,
                    Event(
                        type="assistant.delta",
                        session_id=job.session_id,
                        data={"id": job.id, "text": text, "offset": offset, "first_token_ms": job.first_token_ms},
                    ),
                )

    async def _summary_messages(self, job: AssistantJob, snapshot: ContextSnapshot, settings: LLMSettings) -> list[ChatCompletionMessageParam]:
        task = TASKS["summary"] + f"\n课程：{snapshot.session.course_name}"
        compression = "按原顺序提炼事实、概念、例子、重点和作业，不得补充原文之外的信息。用简短要点，保留不确定性。"
        budget = settings.context_characters - len(SYSTEM) - max(len(task), len(compression) + 60)
        chunks = list(summary_chunks(self.store, snapshot, characters=budget))
        for _round in range(8):
            if len(chunks) <= 1:
                self._progress(job, "正在整理完整课堂笔记")
                return summary_prompt(chunks[0] if chunks else "", task)
            summaries: list[str] = []
            for index, chunk in enumerate(chunks):
                self._progress(job, f"正在整理第 {index + 1}/{len(chunks)} 段")
                instruction = compression + f"\n控制在 {max(100, budget // 4)} 字以内。"
                summaries.append(await self._compress(job, summary_prompt(chunk, instruction), settings))
            combined = "\n\n".join(summaries)
            if len(combined) >= sum(map(len, chunks)):
                raise LLMError("summary_not_reduced", "模型未能压缩长课堂内容；请换用更强模型或增加上下文上限后重试")
            chunks = split_text(combined, budget)
        raise LLMError("summary_too_large", "课堂内容超过当前模型的整理能力；请增加上下文上限或换用其他模型")

    async def _compress(self, job: AssistantJob, messages: list[ChatCompletionMessageParam], settings: LLMSettings) -> str:
        job.provider_calls += 1
        async with aclosing(self.llm.stream(settings, messages, max_tokens=min(2048, settings.context_characters // 4))) as response:
            return "".join([text async for text in response])


def summary_prompt(text: str, task: str) -> list[ChatCompletionMessageParam]:
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}, {"role": "user", "content": task}]


def split_text(text: str, characters: int) -> list[str]:
    return [text[start : start + characters] for start in range(0, len(text), characters)]
