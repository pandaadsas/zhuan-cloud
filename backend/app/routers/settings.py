"""系统设置：API Key 与模型选择（存库即时生效，供组员各自填 Key 测试）。"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from openai import OpenAI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config_runtime import get_cfg, invalidate
from ..database import SessionLocal, get_db
from ..models import AppConfig, User

logger = logging.getLogger("zhuan.settings")
router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsIn(BaseModel):
    mock_mode: bool = False
    api_key: str = ""
    text_model: str = ""
    vl_model: str = ""
    embed_model: str = ""
    asr_model: str = ""


class TestIn(BaseModel):
    api_key: str = ""
    model: str = "qwen-flash"


def _mask(k: str) -> str:
    if not k:
        return ""
    return k[:7] + "****" + k[-4:] if len(k) > 14 else "已配置"


@router.get("")
def read_settings(user: User = Depends(get_current_user)):
    cfg = get_cfg()
    return {
        "mock_mode": cfg.mock_mode,
        "has_key": bool(cfg.dashscope_api_key),
        "api_key_masked": _mask(cfg.dashscope_api_key),
        "text_model": cfg.qwen_text_model,
        "vl_model": cfg.qwen_vl_model,
        "embed_model": cfg.qwen_embed_model,
        "asr_model": cfg.qwen_asr_model,
        "updated_at": cfg.updated_at,
    }


@router.put("")
def save_settings(payload: SettingsIn, user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        row = db.get(AppConfig, 1) or AppConfig(id=1)
        row.data = {
            "mock_mode": payload.mock_mode,
            "api_key": payload.api_key.strip(),
            "text_model": payload.text_model.strip(),
            "vl_model": payload.vl_model.strip(),
            "embed_model": payload.embed_model.strip(),
            "asr_model": payload.asr_model.strip(),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "updated_by": user.name,
        }
        row.updated_at = datetime.now()
        db.add(row)
        db.commit()
    finally:
        db.close()
    invalidate()
    logger.info("系统设置已更新 by=%s mock_mode=%s api_key=%s models=text:%s,vl:%s,embed:%s,asr:%s",
                user.name, payload.mock_mode, _mask(payload.api_key.strip()),
                payload.text_model, payload.vl_model, payload.embed_model, payload.asr_model)
    return {"ok": True}


@router.post("/test")
def test_connection(payload: TestIn, user: User = Depends(get_current_user)):
    cfg = get_cfg()
    key = payload.api_key.strip() or cfg.dashscope_api_key
    if not key:
        return {"ok": False, "error": "尚未配置 API Key"}
    try:
        c = OpenAI(api_key=key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", timeout=20)
        r = c.chat.completions.create(
            model=payload.model or cfg.qwen_text_model,
            messages=[{"role": "user", "content": "回复OK两个字"}],
            max_tokens=8,
        )
        return {"ok": True, "reply": r.choices[0].message.content.strip(), "model": payload.model}
    except Exception as e:
        logger.warning("AI 连接测试失败 model=%s error=%s", payload.model, str(e)[:220])
        return {"ok": False, "error": str(e)[:220]}
