"""运行时动态配置：设置页保存的 API Key / 模型选择存入数据库，运行时即时生效（3秒缓存）。"""
import threading
import time
from types import SimpleNamespace

from .database import SessionLocal
from .models import AppConfig

_lock = threading.Lock()
_cache = {"data": None, "at": 0.0}


def _load_db():
    db = SessionLocal()
    try:
        row = db.get(AppConfig, 1)
        return (row.data or None) if row else None
    except Exception:
        return None
    finally:
        db.close()


def get_cfg():
    with _lock:
        now = time.time()
        if _cache["data"] is None or now - _cache["at"] > 3:
            db_data = _load_db()
            _cache["data"] = db_data or {}
            _cache["at"] = now

    from .config import settings

    d = _cache["data"]
    return SimpleNamespace(
        mock_mode=bool(d.get("mock_mode", settings.mock_mode)),
        dashscope_api_key=d.get("api_key") or settings.dashscope_api_key,
        qwen_text_model=d.get("text_model") or settings.qwen_text_model,
        qwen_vl_model=d.get("vl_model") or settings.qwen_vl_model,
        qwen_embed_model=d.get("embed_model") or settings.qwen_embed_model,
        qwen_asr_model=d.get("asr_model") or settings.qwen_asr_model,
        updated_at=d.get("updated_at"),
    )


def invalidate():
    with _lock:
        _cache["at"] = 0.0
