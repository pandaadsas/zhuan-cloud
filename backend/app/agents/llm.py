"""LLM 抽象层：mock_mode=True 或未配置 key 时所有能力走内置模拟引擎，零 API 消耗。"""
import json
import logging

from openai import OpenAI

from ..config import settings

logger = logging.getLogger("zhuan.llm")

_client: OpenAI | None = None


def llm_ready() -> bool:
    return (not settings.mock_mode) and bool(settings.dashscope_api_key)


def client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.dashscope_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=60,
        )
    return _client


def chat_json(system: str, user: str) -> dict | None:
    """真实模式调 LLM 返回 JSON；模拟模式/调用失败返回 None，调用方降级走规则逻辑。"""
    if not llm_ready():
        return None
    try:
        resp = client().chat.completions.create(
            model=settings.qwen_text_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning("LLM JSON调用失败，降级规则引擎：%s", e)
        return None


def chat_text(system: str, user: str) -> str | None:
    """真实模式调 LLM 返回文本；模拟模式/调用失败返回 None。"""
    if not llm_ready():
        return None
    try:
        resp = client().chat.completions.create(
            model=settings.qwen_text_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
        )
        return resp.choices[0].message.content
    except Exception as e:
        logger.warning("LLM 文本调用失败，降级模板引擎：%s", e)
        return None
