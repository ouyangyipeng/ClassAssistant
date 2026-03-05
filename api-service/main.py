"""
上课摸鱼搭子 - FastAPI 后端入口
================================
启动命令: uvicorn main:app --host 0.0.0.0 --port 8765 --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

# 加载环境变量
load_dotenv()

# 创建 FastAPI 应用实例
app = FastAPI(
    title="上课摸鱼搭子 - 后端服务",
    description="大学课堂辅助工具的后端 API 服务",
    version="0.1.0"
)

# 配置 CORS，允许 Tauri 前端访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tauri 使用自定义协议，这里放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保 data 目录存在
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---- 注册路由 (后续步骤中实现) ----
from routers import ppt_router, monitor_router, rescue_router, summary_router

app.include_router(ppt_router.router, prefix="/api", tags=["PPT 解析"])
app.include_router(monitor_router.router, prefix="/api", tags=["监控服务"])
app.include_router(rescue_router.router, prefix="/api", tags=["救场功能"])
app.include_router(summary_router.router, prefix="/api", tags=["课后总结"])


@app.get("/")
async def root():
    """健康检查接口"""
    return {"status": "ok", "message": "上课摸鱼搭子后端服务运行中 🎣"}


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
