"""隐患信息抽取：真实模式=qwen结构化抽取；模拟模式=规则引擎（关键词+正则）。"""
import re

from .llm import chat_json

# 隐患类型识别规则：关键词 -> (标准类型, 基础风险等级)
HAZARD_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("违规吸烟", "吸烟", "烟头"), "消防安全-违规吸烟", "中"),
    (("消防通道", "占用", "堵塞通道"), "消防安全-通道占用", "中"),
    (("灭火器", "消防栓"), "消防安全-设施缺失", "中"),
    (("动火", "电焊", "焊接", "气割", "明火"), "动火作业", "高"),
    (("临边", "防护栏杆", "栏杆缺失", "防护缺失"), "高处作业-临边防护", "高"),
    (("洞口", "电梯井", "预留洞", "井口"), "高处作业-洞口防护", "高"),
    (("安全帽",), "个人防护-安全帽", "中"),
    (("安全带", "系挂"), "个人防护-安全带", "高"),
    (("脚手架", "剪刀撑", "扫地杆"), "脚手架工程", "高"),
    (("模板支撑", "支模架"), "模板支撑体系", "高"),
    (("配电箱", "电缆", "临时用电", "漏电", "私拉乱接"), "临时用电", "中"),
    (("塔吊", "起重", "吊装", "吊运"), "起重吊装", "高"),
    (("基坑", "支护", "边坡", "坍塌"), "基坑工程", "高"),
    (("升降机", "施工电梯"), "施工升降机", "高"),
    (("垃圾", "渣土", "的建筑垃圾"), "文明施工-垃圾清理", "低"),
    (("材料", "堆放", "码放", "乱堆"), "材料堆放", "低"),
    (("扬尘", "裸土", "覆盖", "道路污染"), "绿色施工-扬尘治理", "低"),
    (("宿舍", "生活区", "食堂"), "生活区管理", "低"),
]

# 隐患类型 -> 分包承包范围关键词（与种子数据中的分包 scope 字符串对应）
SCOPE_KEYWORDS = {
    "高处作业-临边防护": "主体结构",
    "高处作业-洞口防护": "主体结构",
    "脚手架工程": "脚手架",
    "模板支撑体系": "模板支撑",
    "动火作业": "机电安装",
    "临时用电": "临时用电",
    "起重吊装": "起重",
    "施工升降机": "升降机",
    "基坑工程": "基坑",
    "个人防护-安全帽": "劳务",
    "个人防护-安全带": "劳务",
    "消防安全-违规吸烟": "文明施工",
    "消防安全-通道占用": "消防通道",
    "消防安全-设施缺失": "消防",
    "文明施工-垃圾清理": "垃圾",
    "材料堆放": "文明施工",
    "绿色施工-扬尘治理": "扬尘",
    "生活区管理": "生活区",
    "其他-待归类": "文明施工",
}

RISK_ORDER = {"低": 0, "中": 1, "高": 2, "重大": 3}

_BUILDING_RE = re.compile(r"(\d{1,2})\s*[#号楼栋]")
_FLOOR_RE = re.compile(r"(?:B\d{1,2}|负?\d{1,2})\s*层")
_SPOT_RE = re.compile(r"(东南角|西南角|东北角|西北角|东侧|西侧|南侧|北侧|中庭|大门口|地下室|屋面|楼梯间|通道旁)")


def extract_by_rules(text: str) -> dict:
    building, floor, spot = "", "", ""
    m = _BUILDING_RE.search(text)
    if m:
        building = f"{m.group(1)}号楼"
    m = _FLOOR_RE.search(text)
    if m:
        floor = m.group(0).replace(" ", "")
    m = _SPOT_RE.search(text)
    if m:
        spot = m.group(1)

    hazard_type, base_risk = "其他-待归类", "中"
    hits = []
    for keywords, htype, risk in HAZARD_RULES:
        if any(k in text for k in keywords):
            hits.append((htype, risk))
    if hits:
        hazard_type = hits[0][0]
        base_risk = max((h[1] for h in hits), key=lambda r: RISK_ORDER[r])

    return {
        "building": building,
        "floor": floor,
        "spot": spot,
        "hazard_type": hazard_type,
        "description": text.strip(),
        "risk_level": base_risk,
        "engine": "智能抽取引擎",
    }


EXTRACT_SYSTEM_PROMPT = """你是建筑施工安全管理专家。从安全员上报的原始描述中抽取结构化隐患信息，输出JSON：
{"building": "楼号如1号楼，没有则空串", "floor": "楼层如12层/B1层，没有则空串", "spot": "具体部位如东侧/楼梯间，没有则空串",
 "hazard_type": "隐患类型，从以下选择：消防安全-违规吸烟|消防安全-通道占用|消防安全-设施缺失|动火作业|高处作业-临边防护|高处作业-洞口防护|个人防护-安全帽|个人防护-安全带|脚手架工程|模板支撑体系|临时用电|起重吊装|基坑工程|施工升降机|文明施工-垃圾清理|材料堆放|绿色施工-扬尘治理|生活区管理|其他-待归类",
 "description": "规范化的隐患描述，保留关键事实，50字以内",
 "risk_level": "风险等级初判：低|中|高|重大"}
只输出JSON，不要多余文字。"""


def extract_hazard(text: str) -> dict:
    """真实模式优先 LLM 结构化抽取，失败或模拟模式回退规则引擎。"""
    result = chat_json(EXTRACT_SYSTEM_PROMPT, text)
    if result and result.get("hazard_type"):
        result["engine"] = "通义千问AI抽取"
        return result
    return extract_by_rules(text)


def need_clarify(ext: dict) -> bool:
    """位置和类型都缺失时需要追问。"""
    return not ext.get("building") and ext.get("hazard_type") in ("其他-待归类", "", None)
