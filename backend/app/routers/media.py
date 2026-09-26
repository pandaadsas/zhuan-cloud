"""媒体接口：语音转写 / 图片隐患识别 / 通用文件上传。"""
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..config import settings
from ..database import get_db
from ..services.asr import transcribe
from ..services.vision import analyze_image

router = APIRouter(prefix="/api", tags=["media"])


def _save_upload(file: UploadFile, sub: str) -> tuple[Path, str]:
    suffix = Path(file.filename or "file.bin").suffix or ".bin"
    name = f"{uuid.uuid4().hex}{suffix}"
    folder = settings.upload_dir / sub
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    with open(path, "wb") as f:
        f.write(file.file.read())
    return path, f"/uploads/{sub}/{name}"


@router.post("/asr")
async def asr(file: UploadFile, user=Depends(require_roles("safety_officer", "safety_supervisor"))):
    path, _ = _save_upload(file, "audio")
    return transcribe(str(path))


@router.post("/vision")
async def vision(file: UploadFile, user=Depends(require_roles("safety_officer", "safety_supervisor"))):
    path, url = _save_upload(file, "images")
    result = analyze_image(str(path), file.content_type or "image/jpeg")
    return {"analysis": result["analysis"], "engine": result["engine"], "image_url": url}


@router.post("/uploads")
async def uploads(file: UploadFile, user=Depends(get_current_user)):
    path, url = _save_upload(file, "misc")
    return {"url": url}
