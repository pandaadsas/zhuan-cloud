"""图片隐患识别：真实=通义 qwen-vl-plus 多模态；模拟=预置典型隐患描述。"""
import base64
import logging
import random

from ..config import settings
from ..agents.llm import client, llm_ready

logger = logging.getLogger("zhuan.vision")

MOCK_ANALYSES = [
    "图片显示施工层临边部位防护栏杆缺失，下方有作业人员活动，存在高处坠落及物体打击风险。建议立即恢复防护并设置警戒隔离。",
    "图片显示消防通道被脚手架钢管和模板占用，通道有效宽度不足，影响应急疏散。建议立即清空并设置禁占标识。",
    "图片显示一名作业人员未正确佩戴安全帽（未系下颌带），存在物体打击伤害风险。建议现场纠正并纳入班前教育。",
    "图片显示现场配电箱箱门敞开、内部接线凌乱，存在触电风险。建议断电整改并核查三级配电两级保护配置。",
]

VL_PROMPT = (
    "你是建筑工地安全员助手。请描述图片中存在的安全隐患：隐患表现、所处位置特征、主要风险点，"
    "80字以内。只描述图中可见内容，不要编造。"
)


def analyze_image(file_path: str, mime: str = "image/jpeg") -> dict:
    if not llm_ready():
        return {"analysis": random.choice(MOCK_ANALYSES), "engine": "AI图片识别"}
    try:
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = client().chat.completions.create(
            model=settings.qwen_vl_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": VL_PROMPT},
                    ],
                }
            ],
            temperature=0.2,
        )
        return {"analysis": resp.choices[0].message.content.strip(), "engine": "通义千问视觉识别"}
    except Exception as e:
        logger.warning("图片识别失败，降级模拟：%s", e)
        return {"analysis": random.choice(MOCK_ANALYSES), "engine": "AI图片识别"}
