"""
上课摸鱼搭子 - FastAPI 后端入口
================================
启动命令: uvicorn main:app --host 0.0.0.0 --port 8765 --reload
"""

import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 加载环境变量 —— 明确指定 .env 路径，避免打包版加载到开发目录的 .env
_env_path_override = os.getenv("CLASSFOX_ENV_PATH")
if _env_path_override:
    _dotenv_path = os.path.abspath(_env_path_override)
elif getattr(sys, 'frozen', False):
    _dotenv_path = os.path.join(os.path.dirname(sys.executable), '.env')
else:
    _dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_dotenv_path)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="上课摸鱼搭子 - 后端服务",
    description="大学课堂辅助工具的后端 API 服务",
    version="1.0.1"
)

# 配置 CORS，允许 Tauri 前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri 使用自定义协议，这里放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保 data 目录存在（由 config.py 自动创建）
from config import DATA_DIR

# ---- 注册路由 (后续步骤中实现) ----
from routers import ppt_router, monitor_router, rescue_router, summary_router, settings_router

app.include_router(ppt_router.router, prefix="/api", tags=["PPT 解析"])
app.include_router(monitor_router.router, prefix="/api", tags=["监控服务"])
app.include_router(rescue_router.router, prefix="/api", tags=["救场功能"])
app.include_router(summary_router.router, prefix="/api", tags=["课后总结"])
app.include_router(settings_router.router, prefix="/api", tags=["设置"])


@app.get("/")
async def root():
    """健康检查接口"""
    return {"status": "ok", "message": "上课摸鱼搭子后端服务运行中 🎣"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "data_dir": DATA_DIR}


if __name__ == "__main__":
    import uvicorn

    # PyInstaller console=False 时 stdout/stderr 为 None，需重定向防止崩溃
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    port = int(os.getenv("API_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
