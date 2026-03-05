"""
LLM 服务
========
调用 OpenAI Compatible API 进行课堂问答分析和课后总结
"""

import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


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
            import json
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
