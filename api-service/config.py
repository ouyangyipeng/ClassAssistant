"""
全局配置
========
集中管理 DATA_DIR 等路径，兼容开发模式和 PyInstaller 打包模式
"""

import os
import sys

_runtime_root = os.getenv("CLASSFOX_PROJECT_ROOT")

if _runtime_root:
    PROJECT_ROOT = os.path.abspath(_runtime_root)
elif getattr(sys, 'frozen', False):
    # PyInstaller 打包模式：exe 位于 release/backend/，data 在 release/data/
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    PROJECT_ROOT = os.path.dirname(_exe_dir)
else:
    # 开发模式：本文件位于 api-service/config.py，项目根目录在上一级
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CITE_DIR = os.path.join(DATA_DIR, "cite")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "summaries"), exist_ok=True)
os.makedirs(CITE_DIR, exist_ok=True)

# 启动日志：方便确认打包版路径是否正确
try:
    _log_path = os.path.join(PROJECT_ROOT, "data", "_startup.log")
    with open(_log_path, "w", encoding="utf-8") as _f:
        _f.write(f"frozen={getattr(sys, 'frozen', False)}\n")
        _f.write(f"executable={sys.executable}\n")
        _f.write(f"PROJECT_ROOT={PROJECT_ROOT}\n")
        _f.write(f"DATA_DIR={DATA_DIR}\n")
except Exception:
    pass
