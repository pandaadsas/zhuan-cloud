"""LLM 抽象层：运行时配置优先（设置页动态生效），未配置回退 .env。

mock_mode=True 或未配置 key 时返回 None，调用方降级走内置模拟引擎，零 API 消耗。
"""
import json
import logging

from openai import OpenAI

from ..config_runtime import get_cfg

logger = logging.getLogger("zhuan.llm")

_clients: dict[str, OpenAI] = {}


def llm_ready(cfg=None) -> bool:
    cfg = cfg or get_cfg()
    return (not cfg.mock_mode) and bool(cfg.dashscope_api_key)


def client(cfg=None) -> OpenAI:
    cfg = cfg or get_cfg()
    key = cfg.dashscope_api_key
    if key not in _clients:
        _clients[key] = OpenAI(
            api_key=key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=60,
        )
    return _clients[key]


def chat_json(system: str, user: str) -> dict | None:
    """真实模式调 LLM 返回 JSON；模拟模式/调用失败返回 None，调用方降级走规则逻辑。"""
    cfg = get_cfg()
    if not llm_ready(cfg):
        return None
    try:
        resp = client(cfg).chat.completions.create(
            model=cfg.qwen_text_model,
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
    cfg = get_cfg()
    if not llm_ready(cfg):
        return None
    try:
        resp = client(cfg).chat.completions.create(
            model=cfg.qwen_text_model,
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
