import asyncio
import io
import os
import sys
from pathlib import Path

import pytest
from docx import Document

from classfox.document_process import parse_isolated
from classfox.documents import DocumentError


async def test_owned_parser_extracts_unicode_office_text_and_sanitizes_errors() -> None:
    document = Document()
    document.add_paragraph("课堂资料 🦊 不丢失")
    buffer = io.BytesIO()
    document.save(buffer)
    assert await parse_isolated(buffer.getvalue(), "中文 名称.docx") == "课堂资料 🦊 不丢失"
    with pytest.raises(DocumentError, match="损坏"):
        await parse_isolated(b"broken", "test.pdf")
    assert await parse_isolated("中文原文".encode(), "notes.md") == "中文原文"


@pytest.mark.parametrize("cancel", [False, True])
async def test_timeout_or_request_cancellation_closes_only_owned_parser_and_removes_input(tmp_path: Path, cancel: bool) -> None:
    marker = tmp_path / "process.txt"
    script = tmp_path / "slow.py"
    script.write_text(
        "import json,os,sys,time\nfrom pathlib import Path\npayload=json.loads(sys.stdin.readline())\n"
        f"Path({str(marker)!r}).write_text(str(os.getpid())+'\\n'+payload['path'])\ntime.sleep(60)\n"
    )
    parsing = asyncio.create_task(parse_isolated(b"private synthetic test text", "test.txt", timeout=2, command=[sys.executable, str(script)]))
    async with asyncio.timeout(2):
        while not marker.exists():
            await asyncio.sleep(0.01)
    pid, input_path = marker.read_text().splitlines()
    assert Path(input_path).exists()
    if cancel:
        parsing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await parsing
    else:
        with pytest.raises(DocumentError, match="超过"):
            await parsing
    assert not Path(input_path).exists()
    if os.name != "nt":
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid), 0)
