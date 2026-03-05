"""
救场功能路由
============
点名触发后，调用 LLM 生成课堂上下文、问题和答案
"""

from fastapi import APIRouter, HTTPException
from services.llm_service import LLMService
from services.transcript_service import TranscriptService

router = APIRouter()

# 服务实例
llm_service = LLMService()
transcript_service = TranscriptService()


@router.post("/emergency_rescue")
async def emergency_rescue():
    """
    紧急救场接口
    - 读取最近 2 分钟的课堂转录文本
    - 读取课程 PPT 材料作为背景知识
    - 调用 LLM 提取老师问题并生成答案
    - 返回：课堂上下文、问题、建议答案
    """
    try:
        # 获取最近的转录文本
        recent_transcript = transcript_service.get_recent_transcript(minutes=2)
        # 获取课程资料
        class_material = transcript_service.get_class_material()

        if not recent_transcript:
            return {
                "status": "warning",
                "context": "暂无课堂记录",
                "question": "未检测到具体问题",
                "answer": "请注意听老师的问题"
            }

        # 调用 LLM 分析
        result = await llm_service.analyze_rescue(
            transcript=recent_transcript,
            material=class_material
        )

        return {
            "status": "success",
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"救场失败: {str(e)}")
