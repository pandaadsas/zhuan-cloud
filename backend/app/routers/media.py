"""媒体接口：语音转写 / 图片隐患识别 / 通用文件上传。"""
import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..config import settings
from ..database import get_db
from ..services.asr import transcribe
from ..services.vision import analyze_image

logger = logging.getLogger("zhuan.media")
router = APIRouter(prefix="/api", tags=["media"])


def _save_upload(file: UploadFile, sub: str) -> tuple[Path, str]:
    suffix = Path(file.filename or "file.bin").suffix or ".bin"
    name = f"{uuid.uuid4().hex}{suffix}"
    folder = settings.upload_dir / sub
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    data = file.file.read()
    with open(path, "wb") as f:
        f.write(data)
    logger.info("文件上传 category=%s origin=%s size=%dB -> %s", sub, file.filename, len(data), path)
    return path, f"/uploads/{sub}/{name}"


@router.post("/asr")
async def asr(file: UploadFile, user=Depends(require_roles("safety_officer", "safety_supervisor"))):
    path, _ = _save_upload(file, "audio")
    start = time.perf_counter()
    result = transcribe(str(path))
    logger.info("语音转写完成 engine=%s 耗时%.0fms", result.get("engine", "?"), (time.perf_counter() - start) * 1000)
    return result


@router.post("/vision")
async def vision(file: UploadFile, user=Depends(require_roles("safety_officer", "safety_supervisor"))):
    path, url = _save_upload(file, "images")
    start = time.perf_counter()
    result = analyze_image(str(path), file.content_type or "image/jpeg")
    logger.info("图片识别完成 engine=%s 耗时%.0fms", result["engine"], (time.perf_counter() - start) * 1000)
    return {"analysis": result["analysis"], "engine": result["engine"], "image_url": url}


@router.post("/uploads")
async def uploads(file: UploadFile, user=Depends(get_current_user)):
    path, url = _save_upload(file, "misc")
    return {"url": url}
