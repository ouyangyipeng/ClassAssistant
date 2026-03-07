"""
LLM 服务
========
调用 OpenAI Compatible API 进行课堂问答分析和课后总结
"""

import os
import logging
import json
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class LLMService:
    """大语言模型调用服务 - 兼容 OpenAI API"""

    def __init__(self):
        # 从环境变量读取配置
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")

        # 初始化异步客户端
        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    async def analyze_rescue(self, transcript: str, material: str) -> dict:
        """
        紧急救场分析
        - 根据课堂转录和课程资料，提取老师的问题并生成答案

        Args:
            transcript: 最近的课堂转录文本
            material: 课程 PPT 资料文本

        Returns:
            包含 context, question, answer 的字典
        """
        # 组装 Prompt
        system_prompt = """你是一个大学课堂助手。你的任务是根据课堂录音转录和课程资料，快速分析以下内容：
1. 目前课堂正在讲的内容概要（简短）
2. 老师刚才提出的问题是什么（精确提取）
3. 该问题的建议答案（结合课程资料给出准确、简洁的回答）

请用以下 JSON 格式回复（不要加 markdown 代码块标记）：
{
    "context": "课堂内容概要",
    "question": "老师提出的问题",
    "answer": "建议答案"
}"""

        user_prompt = f"""【课堂录音转录（最近2分钟）】
{transcript}

【课程资料（PPT内容）】
{material if material else "暂无课程资料"}

请分析并提取问题和答案。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # 低温度，提高准确性
                max_tokens=1000,
            )

            # 解析 LLM 返回的 JSON
            content = response.choices[0].message.content.strip()

            # 尝试解析 JSON
            try:
                result = json.loads(content)
                return {
                    "context": result.get("context", "无法提取课堂内容"),
                    "question": result.get("question", "无法识别问题"),
                    "answer": result.get("answer", "无法生成答案")
                }
            except json.JSONDecodeError:
                # 如果 LLM 没有返回有效 JSON，直接返回原文
                return {
                    "context": "正在解析中...",
                    "question": "请查看课堂内容",
                    "answer": content
                }

        except Exception as e:
            return {
                "context": "LLM 调用失败",
                "question": str(e),
                "answer": "请检查 API 配置是否正确"
            }

    async def analyze_catchup(self, transcript: str, material: str) -> dict:
        """
        课堂进度摘要 - 告知用户老师讲到哪了、有什么重要信息

        Args:
            transcript: 最近的课堂转录文本
            material: 课程 PPT 资料文本

        Returns:
            包含 summary 的字典
        """
        system_prompt = """你是一个大学课堂助手。学生正在上课但没有认真听，现在想知道老师讲到哪了。
请根据课堂录音转录和课程资料，简洁地总结：
1. 老师目前讲到了什么内容
2. 有没有重要的知识点、考试重点或需要注意的事项
3. 如果有布置作业或提到截止日期，也请标出

请用简洁易读的中文回复，不要太长，控制在200字以内。"""

        user_prompt = f"""【课堂录音转录】
{transcript}

【课程资料（PPT内容）】
{material if material else "暂无课程资料"}

请总结老师讲到哪了。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=500,
            )
            content = response.choices[0].message.content.strip()
            return {"summary": content}
        except Exception as e:
            return {"summary": f"LLM 调用失败: {str(e)}，请检查 API 配置"}

    async def answer_catchup_question(
        self,
        summary: str,
        transcript: str,
        material: str,
        question: str,
        history: list[dict] | None = None,
    ) -> dict:
        """围绕当前课堂进度继续追问。"""
        safe_history = history or []
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in safe_history[-8:]
            if item.get('content')
        ) or "暂无历史追问"

        system_prompt = """你是一个课堂随堂答疑助手。你需要基于当前课堂进度摘要、最近课堂转录、课程资料以及已有追问历史，回答学生的后续问题。

要求：
1. 优先依据给定上下文回答，不要编造课堂里没提过的结论。
2. 回答要直接、清楚，适合学生边上课边看。
3. 如果问题是解释术语、公式或概念，可以补充必要背景，但不要长篇展开。
4. 如果上下文不足，要明确说明“当前课堂上下文不足”，再给出谨慎推断。"""

        user_prompt = f"""【当前课堂进度摘要】
{summary}

【最近课堂转录】
{transcript}

【课程资料】
{material if material else '暂无课程资料'}

【已有追问历史】
{history_text}

【学生的新问题】
{question}

请直接回答学生。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=800,
            )
            content = (response.choices[0].message.content or "").strip()
            return {"answer": content or "当前没有可用回答。"}
        except Exception as exc:
            return {"answer": f"LLM 调用失败: {exc}，请检查 API 配置"}

    async def answer_rescue_question(
        self,
        context: str,
        extracted_question: str,
        suggested_answer: str,
        transcript: str,
        material: str,
        followup: str,
        history: list[dict] | None = None,
    ) -> dict:
        """围绕救场结果继续追问。"""
        safe_history = history or []
        history_text = "\n".join(
            f"{item.get('role', 'user')}: {item.get('content', '')}"
            for item in safe_history[-8:]
            if item.get('content')
        ) or "暂无历史追问"

        system_prompt = """你是一个课堂救场辅助助手。你需要基于当前课堂上下文、识别到的老师问题、已有建议答案、最近课堂转录、课程资料以及追问历史，继续回答学生的后续问题。

要求：
1. 优先依据当前课堂上下文和已给出的救场答案作答，不要无依据扩展。
2. 回答要适合学生临场查看，简洁直接。
3. 如果上下文不足，要明确指出“当前课堂上下文不足”，再给出谨慎推断。
4. 如果学生是在追问如何表达，可以给出更口语化、更短的回答版本。"""

        user_prompt = f"""【课堂上下文】
{context}

【识别到的老师问题】
{extracted_question}

【当前建议答案】
{suggested_answer}

【最近课堂转录】
{transcript}

【课程资料】
{material if material else '暂无课程资料'}

【已有追问历史】
{history_text}

【学生的新问题】
{followup}

请直接回答学生。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.4,
                max_tokens=800,
            )
            content = (response.choices[0].message.content or "").strip()
            return {"answer": content or "当前没有可用回答。"}
        except Exception as exc:
            return {"answer": f"LLM 调用失败: {exc}，请检查 API 配置"}

    async def generate_class_summary(self, transcript: str, material: str) -> str:
        """
        生成课后总结 Markdown 笔记

        Args:
            transcript: 完整的课堂转录文本
            material: 课程 PPT 资料文本

        Returns:
            Markdown 格式的课堂总结
        """
        system_prompt = """你是一个专业的课堂笔记整理助手。请根据课堂录音转录和课程资料，生成一份结构化的 Markdown 课堂笔记。

笔记应包含以下章节：
# 📚 课堂笔记

## 📝 课程概要
（简要描述本节课的主题和内容）

## 🔑 核心知识点
（列出本节课的重要知识点，用编号列表）

## 💡 老师重点强调
（老师特别强调或反复提到的内容）

## 📋 作业与任务
（如果提到了作业、小测、DDL 等，列出来）

## ❓ 课堂问答
（记录课上的提问和回答）

## 📌 补充说明
（其他值得注意的信息）

请确保笔记内容准确、条理清晰。"""

        user_prompt = f"""【完整课堂转录】
{transcript}

【课程资料（PPT内容）】
{material if material else "暂无课程资料"}

请生成课堂笔记。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                max_tokens=4000,
            )
            return response.choices[0].message.content.strip()

        except Exception as e:
            return f"# ⚠️ 总结生成失败\n\n错误信息: {str(e)}\n\n请检查 LLM API 配置。"

    async def compress_monitoring_progress(self, previous_summary: str, recent_lines: list[str]) -> str:
        """
        将历史摘要和新近课堂记录压缩为新的滚动摘要。

        Args:
            previous_summary: 上一次滚动摘要，首次为空字符串
            recent_lines: 本轮待压缩的课堂记录（建议 50 行）

        Returns:
            新的精简摘要文本
        """
        if not recent_lines:
            return previous_summary.strip()

        system_prompt = """你是一个课堂记录压缩助手。你的任务是把“历史摘要”和“最新课堂记录”合并成一份更短但信息完整的滚动摘要。

要求：
1. 保留课程主题、关键知识点、老师强调内容、作业/截止日期、课堂问答。
2. 删除口头重复、语气词、无信息量重复表述。
3. 输出精简中文，不要编造内容。
4. 控制在 300 到 500 字以内。
5. 直接输出摘要正文，不要加 markdown 标题、代码块或额外说明。"""

        previous_summary = previous_summary.strip() or "暂无历史摘要"
        new_content = "\n".join(recent_lines)
        user_prompt = f"""【历史摘要】
{previous_summary}

【最新课堂记录】
{new_content}

请输出新的滚动摘要。"""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=900,
            )
            content = (response.choices[0].message.content or "").strip()
            if not content:
                raise ValueError("LLM 未返回滚动摘要内容")
            return content
        except Exception:
            logger.exception("滚动摘要生成失败")
            raise
