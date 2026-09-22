import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from time import monotonic
from urllib.parse import urlsplit

import httpx
from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, AsyncOpenAI, AsyncStream
from openai.types.chat import ChatCompletionChunk, ChatCompletionMessageParam

from classfox.credentials import Credentials
from classfox.model_process import ModelEndpoint, ModelProcessError
from classfox.settings import LLMSettings


class LLMError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def provider_error(error: APIStatusError) -> LLMError:
    if error.status_code in {401, 403}:
        return LLMError("invalid_key", "模型服务拒绝了凭据，请检查 API Key 和模型权限")
    if error.status_code == 429:
        return LLMError("rate_limited", "模型服务额度不足或请求过多，请检查余额或稍后重试")
    if error.status_code in {400, 404, 422}:
        return LLMError("invalid_model", "模型或接口配置不受支持，请检查服务地址和模型名称")
    return LLMError("provider_unavailable", "模型服务暂时不可用，请稍后重试")


class LLMService:
    def __init__(
        self,
        credentials: Credentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        local_model: Callable[[str], Awaitable[ModelEndpoint]] | None = None,
    ) -> None:
        self.credentials = credentials
        self._transport = transport
        self._local_model = local_model

    def context_settings(self, settings: LLMSettings) -> LLMSettings:
        if settings.mode == "local" and settings.managed and self._local_model is not None:
            return settings.model_copy(update={"context_characters": min(settings.context_characters, 6000)})
        return settings

    async def _connection(self, settings: LLMSettings) -> tuple[LLMSettings, str]:
        if settings.mode == "local" and settings.managed:
            if self._local_model is None:
                raise LLMError("local_model_unavailable", "受管本地模型服务尚未就绪")
            try:
                endpoint = await self._local_model(settings.local_model_id)
            except ModelProcessError as error:
                raise LLMError("local_model_unavailable", str(error)) from error
            return settings.model_copy(update={"base_url": endpoint.base_url, "model": endpoint.model}), endpoint.key
        return settings, await self._key(settings)

    async def _key(self, settings: LLMSettings) -> str:
        if settings.mode == "local":
            if urlsplit(settings.base_url).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise LLMError("invalid_endpoint", "本地模式只能连接此电脑上的模型；远程服务请选择 BYOK")
            return "local"
        key = await asyncio.to_thread(self.credentials.get, "llm")
        if not key:
            raise LLMError("missing_key", "请先在设置中填写模型服务的 API Key")
        return key

    async def stream(self, settings: LLMSettings, messages: list[ChatCompletionMessageParam], *, max_tokens: int = 2048) -> AsyncGenerator[str, None]:
        deadline = monotonic() + settings.timeout_seconds
        try:
            async with asyncio.timeout(settings.timeout_seconds):
                settings, key = await self._connection(settings)
            # Each request owns its connection, including cancellation and early generator close.
            async with (
                httpx.AsyncClient(transport=self._transport, trust_env=False, follow_redirects=False) as http,
                AsyncOpenAI(
                    api_key=key, base_url=settings.base_url, http_client=http, timeout=httpx.Timeout(settings.timeout_seconds, connect=5), max_retries=0
                ) as client,
            ):
                async with asyncio.timeout(max(0, deadline - monotonic())):
                    response = await client.chat.completions.create(model=settings.model, messages=messages, stream=True, max_tokens=max_tokens)
                async with response:
                    async for text in self._read(response, deadline):
                        yield text
        except (TimeoutError, APITimeoutError, httpx.TimeoutException) as exc:
            raise LLMError("timeout", "模型响应超时；可以重试，或在设置中调整时限和模型") from exc
        except APIStatusError as exc:
            raise provider_error(exc) from exc
        except (APIConnectionError, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            raise LLMError("connection_failed", "无法连接模型服务，请检查网络或本地模型运行状态") from exc
        except (APIError, ValueError, TypeError, AttributeError) as exc:
            raise LLMError("invalid_response", "模型服务返回了无法解析的内容，请检查接口兼容性") from exc

    @staticmethod
    async def _read(response: AsyncStream[ChatCompletionChunk], deadline: float) -> AsyncIterator[str]:
        iterator = response.__aiter__()
        characters = 0
        finished = False
        while True:
            async with asyncio.timeout(max(0, deadline - monotonic())):
                chunk = await anext(iterator, None)
            if chunk is None:
                break
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            reason = choice.finish_reason
            if reason and reason != "stop":
                raise LLMError("incomplete_response", "模型未完整生成回答；请缩短问题或换用其他模型后重试")
            if choice.delta.content:
                characters += len(choice.delta.content)
                if characters > 64000:
                    raise LLMError("response_too_large", "模型输出过长，已停止接收；请缩小问题范围")
                yield choice.delta.content
            finished = finished or reason == "stop"
        if not finished or not characters:
            raise LLMError("incomplete_response", "模型没有返回完整回答；原始课堂记录仍已保留，可以重试")
