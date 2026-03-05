"""
转录文本服务
============
管理课堂转录文本和课程资料的读写
"""

import os
from datetime import datetime, timedelta

# data 目录路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


class TranscriptService:
    """转录文本管理服务"""

    def __init__(self):
        self.transcript_path = os.path.join(DATA_DIR, "class_transcript.txt")
        self.material_path = os.path.join(DATA_DIR, "current_class_material.txt")

    def get_recent_transcript(self, minutes: int = 2) -> str:
        """
        获取最近 N 分钟的转录文本

        Args:
            minutes: 向前回溯的分钟数，默认 2 分钟

        Returns:
            最近的转录文本
        """
        if not os.path.exists(self.transcript_path):
            return ""

        with open(self.transcript_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if not lines:
            return ""

        # 解析带有时间戳的行，筛选最近 N 分钟的内容
        now = datetime.now()
        cutoff = now - timedelta(minutes=minutes)
        recent_lines = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("==="):
                continue

            # 尝试解析时间戳格式 [HH:MM:SS]
            if line.startswith("[") and "]" in line:
                try:
                    time_str = line[1:line.index("]")]
                    line_time = datetime.strptime(time_str, "%H:%M:%S").replace(
                        year=now.year, month=now.month, day=now.day
                    )
                    if line_time >= cutoff:
                        recent_lines.append(line)
                except ValueError:
                    recent_lines.append(line)  # 解析失败则保留
            else:
                recent_lines.append(line)

        return "\n".join(recent_lines)

    def get_full_transcript(self) -> str:
        """获取完整的课堂转录文本"""
        if not os.path.exists(self.transcript_path):
            return ""

        with open(self.transcript_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_class_material(self) -> str:
        """获取课程 PPT 资料文本"""
        if not os.path.exists(self.material_path):
            return ""

        with open(self.material_path, "r", encoding="utf-8") as f:
            return f.read()
