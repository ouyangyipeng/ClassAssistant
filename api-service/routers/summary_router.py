"""
课后总结路由
============
课后生成 Markdown 笔记
"""

from fastapi import APIRouter, HTTPException
from services.llm_service import LLMService
from services.transcript_service import TranscriptService
import os
from datetime import datetime

router = APIRouter()

llm_service = LLMService()
transcript_service = TranscriptService()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


@router.post("/generate_summary")
async def generate_summary():
    """
    课后总结接口
    - 读取完整的课堂转录文本
    - 读取课程资料
    - 调用 LLM 生成结构化 Markdown 笔记
    - 保存到 /data/summaries/ 目录
    """
    try:
        full_transcript = transcript_service.get_full_transcript()
        class_material = transcript_service.get_class_material()

        if not full_transcript:
            raise HTTPException(status_code=400, detail="没有课堂记录可供总结")

        # 调用 LLM 生成总结
        summary_md = await llm_service.generate_class_summary(
            transcript=full_transcript,
            material=class_material
        )

        # 保存总结文件
        summaries_dir = os.path.join(DATA_DIR, "summaries")
        os.makedirs(summaries_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"课堂笔记_{timestamp}.md"
        filepath = os.path.join(summaries_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(summary_md)

        return {
            "status": "success",
            "filename": filename,
            "summary": summary_md
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"总结生成失败: {str(e)}")
