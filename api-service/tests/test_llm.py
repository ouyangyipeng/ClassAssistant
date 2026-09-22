import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import aclosing

import httpx
import pytest

from classfox.credentials import CredentialName
from classfox.llm import LLMError, LLMService
from classfox.model_process import ModelEndpoint
from classfox.settings import LLMSettings


class TestCredentials:
    __test__ = False

    def __init__(self, value: str | None = "synthetic-provider-key") -> None:
        self.value = value

    def get(self, name: CredentialName) -> str | None:
        return self.value

    def set(self, name: CredentialName, value: str | None) -> None:
        self.value = value


def delta(text: str | None = None, *, finish: str | None = None) -> bytes:
    return ("data: " + json.dumps({"id": "test", "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}) + "\n\n").encode()


class ControlledStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield delta("先回答")
        await self.release.wait()
        yield delta("，再解释。")
        yield delta(finish="stop")
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        self.closed = True


def settings() -> LLMSettings:
    return LLMSettings(mode="byok", base_url="https://provider.example/v1", model="test-model")


async def test_first_delta_arrives_before_completion_and_close_releases_connection() -> None:
    body = ControlledStream()
    requests: list[httpx.Request] = []
    requested = asyncio.Event()

    def provider(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        requested.set()
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)

    service = LLMService(TestCredentials(), transport=httpx.MockTransport(provider))
    async with aclosing(service.stream(settings(), [{"role": "user", "content": "问题"}])) as response:
        first = asyncio.ensure_future(anext(response))
        await asyncio.wait_for(requested.wait(), 20)
        assert await asyncio.wait_for(first, 1) == "先回答"
        assert not body.release.is_set()
    assert body.closed
    payload = json.loads(requests[0].content)
    assert payload["stream"] is True
    assert requests[0].url == "https://provider.example/v1/chat/completions"


@pytest.mark.parametrize("status,code", [(401, "invalid_key"), (429, "rate_limited"), (503, "provider_unavailable")])
async def test_provider_errors_are_sanitized_and_not_retried(status: int, code: str) -> None:
    count = 0

    def provider(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        return httpx.Response(status, json={"error": {"message": "synthetic-provider-key secret echoed by provider"}})

    service = LLMService(TestCredentials(), transport=httpx.MockTransport(provider))
    with pytest.raises(LLMError) as failure:
        await anext(service.stream(settings(), [{"role": "user", "content": "问题"}]))
    assert failure.value.code == code
    assert "synthetic-provider-key" not in str(failure.value)
    assert count == 1


async def test_missing_byok_key_fails_before_any_network_request() -> None:
    def provider(request: httpx.Request) -> httpx.Response:
        pytest.fail("Missing credentials must not contact the provider")

    service = LLMService(TestCredentials(None), transport=httpx.MockTransport(provider))
    with pytest.raises(LLMError, match="API Key"):
        await anext(service.stream(settings(), [{"role": "user", "content": "问题"}]))


@pytest.mark.parametrize("body", [b"data: [DONE]\n\n", delta("unfinished"), delta("refused", finish="content_filter"), delta("too long", finish="length")])
async def test_empty_interrupted_filtered_or_truncated_response_is_not_success(body: bytes) -> None:
    service = LLMService(TestCredentials(), transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body)))
    with pytest.raises(LLMError):
        _ = [text async for text in service.stream(settings(), [{"role": "user", "content": "问题"}])]


async def test_cancel_pending_stream_closes_provider_body() -> None:
    body = ControlledStream()
    service = LLMService(TestCredentials(), transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
    response = service.stream(settings(), [{"role": "user", "content": "问题"}])
    assert await anext(response) == "先回答"
    pending = asyncio.ensure_future(anext(response))
    await asyncio.sleep(0)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert body.closed


async def test_stalled_stream_respects_total_deadline_and_closes() -> None:
    body = ControlledStream()
    service = LLMService(TestCredentials(), transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=body)))
    configuration = settings().model_copy(update={"timeout_seconds": 5})
    async with aclosing(service.stream(configuration, [{"role": "user", "content": "问题"}])) as response:
        assert await anext(response) == "先回答"
        with pytest.raises(LLMError) as failure:
            await asyncio.wait_for(anext(response), 6)
        assert failure.value.code == "timeout"
    assert body.closed


async def test_managed_model_uses_owned_endpoint_token_and_context_limit() -> None:
    async def local_model(model_id: str) -> ModelEndpoint:
        assert model_id == "qwen35-4b"
        return ModelEndpoint("http://127.0.0.1:43123/v1", "synthetic-owned-key")

    def provider(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://127.0.0.1:43123/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-owned-key"
        assert json.loads(request.content)["model"] == "classfox-local"
        return httpx.Response(200, content=delta("答案") + delta(finish="stop") + b"data: [DONE]\n\n")

    service = LLMService(TestCredentials(None), transport=httpx.MockTransport(provider), local_model=local_model)
    configuration = service.context_settings(LLMSettings())
    assert configuration.context_characters == 6000
    assert "".join([text async for text in service.stream(configuration, [{"role": "user", "content": "问题"}])]) == "答案"
