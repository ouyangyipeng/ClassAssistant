"""
PPT 解析路由
============
处理 PPT 文件上传与文本提取
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from services.ppt_service import parse_ppt_to_text
import os

router = APIRouter()

# data 目录路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


@router.post("/upload_ppt")
async def upload_ppt(file: UploadFile = File(...)):
    """
    上传 PPT 文件并解析为纯文本
    - 接收上传的 .pptx 文件
    - 使用 python-pptx 解析出所有幻灯片文本
    - 保存到 /data/current_class_material.txt
    """
    # 校验文件类型
    if not file.filename.endswith(('.pptx', '.ppt')):
        raise HTTPException(status_code=400, detail="仅支持 .pptx 格式的文件")

    try:
        # 读取上传的文件内容
        content = await file.read()

        # 临时保存文件用于解析
        temp_path = os.path.join(DATA_DIR, "temp_upload.pptx")
        with open(temp_path, "wb") as f:
            f.write(content)

        # 调用解析服务
        text = parse_ppt_to_text(temp_path)

        # 将解析结果保存到课程资料文件
        material_path = os.path.join(DATA_DIR, "current_class_material.txt")
        with open(material_path, "w", encoding="utf-8") as f:
            f.write(text)

        # 清理临时文件
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return {
            "status": "success",
            "message": f"成功解析 PPT: {file.filename}",
            "text_length": len(text)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PPT 解析失败: {str(e)}")
