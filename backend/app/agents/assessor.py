"""风险定级 + 处置建议生成：检索到的规范条款作为定级与建议依据。"""
import logging

from .llm import chat_text
from .extractor import RISK_ORDER

logger = logging.getLogger("zhuan.assessor")
REGULATION_CONTEXT_BUDGET = 8000

# 特定类型的风险底线（叠加基础定级，只升不降）
RISK_FLOOR = {
    "动火作业": "高",
    "基坑工程": "高",
    "起重吊装": "高",
    "高处作业-临边防护": "高",
    "高处作业-洞口防护": "高",
    "脚手架工程": "高",
    "模板支撑体系": "高",
    "施工升降机": "高",
    "个人防护-安全带": "高",
    "临时用电": "中",
    "消防安全-违规吸烟": "中",
    "消防安全-通道占用": "中",
}

IMMEDIATE_ACTIONS = {
    "消防安全-违规吸烟": "立即制止吸烟行为，清理火种，对当事人按项目制度进行教育处罚",
    "消防安全-通道占用": "立即组织清空消防通道，设置禁占标识，纳入日常巡查",
    "消防安全-设施缺失": "立即核查消防设施配置，按标准补齐并检查有效性",
    "动火作业": "立即停止违规动火，核查动火审批与看火人配置，清理周边可燃物",
    "高处作业-临边防护": "立即设置警戒隔离，恢复临边防护设施，未恢复前禁止在该区域作业",
    "高处作业-洞口防护": "立即设置硬质围挡或盖板并固定，设置警示标识",
    "个人防护-安全帽": "立即纠正，核查入场安全教育记录，按制度处理",
    "个人防护-安全带": "立即停止相关高处作业，纠正安全带系挂方式后方可恢复作业",
    "脚手架工程": "立即停止该架体上作业，组织专项检查，整改验收后方可恢复",
    "模板支撑体系": "立即停止相关作业，组织技术复核，必要时专项方案论证",
    "临时用电": "立即断电整改，核查三级配电两级保护，整改后验收送电",
    "起重吊装": "立即暂停吊装，核查设备验收、人员资质与警戒措施",
    "施工升降机": "立即停用，组织专项检查，验收合格后恢复使用",
    "基坑工程": "加密监测，核查支护与降排水，异常时立即撤离并启动应急流程",
    "文明施工-垃圾清理": "组织清理，落实分区责任人制度与清运计划",
    "材料堆放": "按平面布置图重新归堆码放，设置标识牌",
    "绿色施工-扬尘治理": "立即覆盖裸土/洒水降尘，落实六个百分之百要求",
    "生活区管理": "组织检查整改，落实生活区管理制度",
}

ASSESS_SYSTEM_PROMPT = """你是建筑工地安全管理专家。根据隐患信息和检索到的规范条款，给出处置建议。
要求：1)以"依据《规范名》条款要求：…"引用检索到的条款；2)按 立即措施/整改要求/预防措施 三段输出；
3)150字以内，务实可执行。直接输出建议正文。
4)规范中的数字、适用条件和禁止事项须有给定条款支持，不得编造；上下文不足时明确说明依据不足。"""


def build_regulation_context(regs: list[dict]) -> str:
    lines = []
    used = 0
    for r in regs[:3]:
        line = f"《{r['doc_name']}》{r['clause_no']} {r['title']}：{r['content']}"
        cost = len(line) + (1 if lines else 0)
        if used + cost > REGULATION_CONTEXT_BUDGET:
            logger.warning("条款上下文预算不足，跳过完整条款 %s %s", r['doc_name'], r['clause_no'])
            continue
        lines.append(line)
        used += cost
    return "\n".join(lines)


def finalize_risk(extracted: dict) -> str:
    """基础定级与类型底线取高者；文本出现'重大危险源/坍塌'等关键词时升级为重大。"""
    level = extracted.get("risk_level") or "中"
    floor = RISK_FLOOR.get(extracted.get("hazard_type", ""))
    if floor and RISK_ORDER[floor] > RISK_ORDER[level]:
        level = floor
    text = extracted.get("description", "")
    if any(k in text for k in ("重大危险源", "大面积坍塌", "人员被困", "坠落已发生")):
        level = "重大"
    return level


def deadline_days(level: str) -> int:
    return {"重大": 1, "高": 2, "中": 3}.get(level, 7)


def build_suggestion(extracted: dict, regs: list[dict]) -> str:
    """真实模式：LLM基于规范条款生成；模拟模式：模板引擎组装（同样引用条款）。"""
    context = build_regulation_context(regs)
    llm_suggestion = chat_text(
        ASSESS_SYSTEM_PROMPT,
        f"隐患：{extracted.get('description', '')}\n类型：{extracted.get('hazard_type', '')}\n"
        f"初判等级：{extracted.get('risk_level', '')}\n检索到的规范条款：\n" + context,
    )
    if llm_suggestion:
        return llm_suggestion

    htype = extracted.get("hazard_type", "")
    immediate = IMMEDIATE_ACTIONS.get(htype, "立即核查现场情况，按项目安全制度组织整改")
    parts = [f"【立即措施】{immediate}。"]
    if regs:
        cites = "；".join(f"《{r['doc_name']}》{r['clause_no']}" for r in regs[:2])
        parts.append(f"【整改依据】{cites}。")
    parts.append(
        f"【整改要求】按风险等级（{extracted.get('risk_level', '中')}）限期整改，整改期间设置警戒标识，"
        "责任班组对照规范逐项落实，完成后提交复查。"
    )
    parts.append("【预防措施】纳入班前教育与日常巡查清单，举一反三排查同类隐患。")
    return "\n".join(parts)
