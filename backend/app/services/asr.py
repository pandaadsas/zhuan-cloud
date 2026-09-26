"""语音转写：真实=通义 qwen3-asr-flash；模拟=预置现场话术（演示零成本）。"""
import logging
import random

from ..config import settings

logger = logging.getLogger("zhuan.asr")

MOCK_TRANSCRIPTS = [
    "3号楼12层东侧临边防护栏杆缺失，旁边有工人在进行二次结构作业。",
    "5号楼一层门口消防通道被钢管模板占用，无法通行。",
    "2号楼6层有工人未戴安全帽在楼内搬运材料。",
    "地下室区域配电箱门未关闭，电缆私拉乱接，存在漏电风险。",
]


def transcribe(file_path: str) -> dict:
    if settings.mock_mode or not settings.dashscope_api_key:
        return {"transcript": random.choice(MOCK_TRANSCRIPTS), "engine": "智能语音识别"}
    try:
        from dashscope import MultiModalConversation

        resp = MultiModalConversation.call(
            model=settings.qwen_asr_model,
            messages=[{"role": "user", "content": [{"audio": f"file://{file_path}"}]}],
        )
        text = resp.output.choices[0].message.content[0]["text"]
        return {"transcript": text, "engine": "智能语音识别"}
    except Exception as e:
        logger.warning("语音识别失败，降级模拟转写：%s", e)
        return {"transcript": random.choice(MOCK_TRANSCRIPTS), "engine": "智能语音识别"}
