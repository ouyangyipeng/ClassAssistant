"""
救场功能路由
============
点名触发后，调用 LLM 生成课堂上下文、问题和答案
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.llm_service import LLMService
from services.transcript_service import TranscriptService

router = APIRouter()

# 服务实例
llm_service = LLMService()
transcript_service = TranscriptService()


class CatchupHistoryItem(BaseModel):
    role: str
    content: str


class CatchupChatRequest(BaseModel):
    summary: str
    question: str
    history: list[CatchupHistoryItem] = []


class RescueChatRequest(BaseModel):
    context: str
    question: str
    answer: str
    followup: str
    history: list[CatchupHistoryItem] = []


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


@router.post("/catchup")
async def catchup():
    """
    老师讲到哪了 - 获取当前课堂进度摘要
    - 读取到目前为止的全部转录文本
    - 读取课程资料
    - 调用 LLM 总结课程进度和重要信息
    """
    try:
        recent_transcript = transcript_service.get_recent_transcript(minutes=10)
        class_material = transcript_service.get_class_material()

        if not recent_transcript:
            return {
                "status": "warning",
                "summary": "暂无课堂记录，请先开始摸鱼模式。"
            }

        result = await llm_service.analyze_catchup(
            transcript=recent_transcript,
            material=class_material
        )

        return {
            "status": "success",
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取进度失败: {str(e)}")


@router.post("/catchup_chat")
async def catchup_chat(request: CatchupChatRequest):
    """围绕当前课堂进度继续追问。"""
    try:
        recent_transcript = transcript_service.get_recent_transcript(minutes=10)
        class_material = transcript_service.get_class_material()
        result = await llm_service.answer_catchup_question(
            summary=request.summary,
            transcript=recent_transcript,
            material=class_material,
            question=request.question,
            history=[item.model_dump() for item in request.history],
        )
        return {
            "status": "success",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"课堂追问失败: {str(e)}")


@router.post("/emergency_rescue_chat")
async def emergency_rescue_chat(request: RescueChatRequest):
    """围绕当前救场分析结果继续追问。"""
    try:
        recent_transcript = transcript_service.get_recent_transcript(minutes=10)
        class_material = transcript_service.get_class_material()
        result = await llm_service.answer_rescue_question(
            context=request.context,
            extracted_question=request.question,
            suggested_answer=request.answer,
            transcript=recent_transcript,
            material=class_material,
            followup=request.followup,
            history=[item.model_dump() for item in request.history],
        )
        return {
            "status": "success",
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"救场追问失败: {str(e)}")
