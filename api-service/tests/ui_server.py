"""Disposable UI test backend: real storage/API and deterministic synthetic generation."""

import asyncio
import json
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import uvicorn

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.credentials import CredentialName
from classfox.settings import LLMSettings, Preferences, SettingsStore


class SyntheticKeys:
    def __init__(self) -> None:
        self.values: dict[CredentialName, str] = {"llm": "synthetic-ui-provider-key"}

    def get(self, name: CredentialName) -> str | None:
        return self.values.get(name)

    def set(self, name: CredentialName, value: str | None) -> None:
        if value is None:
            self.values.pop(name, None)
        else:
            self.values[name] = value


class SampleResponse(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        content = (
            "先序遍历的顺序是：**根节点 → 左子树 → 右子树**。\n\n"
            "例如根节点是 A，左子节点是 B，右子节点是 C，遍历顺序就是 A、B、C。\n\n"
            "### 课堂依据\n\n- 老师介绍了根、左、右的访问顺序。\n- 原文中的作业要求应以课堂记录为准。"
        )
        for index in range(0, len(content), 5):
            await asyncio.sleep(0.08)
            payload = {"id": "ui-fixture", "choices": [{"index": 0, "delta": {"content": content[index : index + 5]}, "finish_reason": None}]}
            yield ("data: " + json.dumps(payload) + "\n\n").encode()
        yield b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        yield b"data: [DONE]\n\n"


def provider(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=SampleResponse())


if __name__ == "__main__":
    directory = Path(tempfile.mkdtemp(prefix="classfox-ui-"))
    SettingsStore(directory / "preferences.json").save(
        Preferences(llm=LLMSettings(mode="byok", base_url="https://provider.example/v1", managed=False, model="synthetic-model"), auto_summary=False)
    )
    app = create_app(
        RuntimeConfig(data_dir=directory, api_token="synthetic-ui-test-token", port=18865),
        credentials=SyntheticKeys(),
        provider_transport=httpx.MockTransport(provider),
    )
    uvicorn.run(app, host="127.0.0.1", port=18865, log_level="warning")
