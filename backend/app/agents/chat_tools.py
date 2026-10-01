"""对话查询工具：Agent 工具执行体 + 规则降级链路共用的查询与组装逻辑。"""
import logging
import re
from collections import Counter

from sqlalchemy.orm import Session

from ..models import OrderEvent, WorkOrder
from ..rag.retriever import search as kb_search
from ..serializers import STATUS_LABELS
from .llm import chat_text, llm_ready

logger = logging.getLogger("zhuan.tools")

_BUILDING_RE = re.compile(r"(\d{1,2})\s*[#号楼栋]")
_FLOOR_RE = re.compile(r"(B\d{1,2}|负?\d{1,2})\s*层")
_ORDER_NO_RE = re.compile(r"ZA-\d{8}-\d{3}")


def classify(msg: str) -> str:
    """规则意图分类：规则降级链路使用（Agent 模式下由 LLM 自主决策）。"""
    if any(k in msg for k in ("周报", "汇总一份", "安全情况汇总", "本周安全")):
        return "weekly"
    if _ORDER_NO_RE.search(msg) or any(
        k in msg for k in ("进度", "到哪一步", "处理到哪", "工单状态", "整改完了吗")
    ):
        return "progress"
    if any(k in msg for k in ("统计", "多少", "几单", "几份", "整改率", "超期", "分布", "情况")):
        return "stats"
    return "kb"


def _order_markdown(db: Session, order: WorkOrder) -> str:
    lines = [
        f"**{order.order_no}｜{order.title}**",
        f"- 当前状态：**{STATUS_LABELS.get(order.status, order.status)}**",
        f"- 风险等级：{order.risk_level}｜责任人：{order.responsible_user.name if order.responsible_user else '未指定'}",
        f"- 整改期限：{order.deadline.strftime('%m-%d %H:%M') if order.deadline else '未设定'}"
        + ("｜⚠️已超期" if order.overdue else ""),
    ]
    lines.append("- 最近流转：")
    recent = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.created_at.desc())
        .limit(4)
        .all()
    )
    for e in reversed(recent):
        lines.append(f"  - {e.created_at.strftime('%m-%d %H:%M')} {e.actor}：{e.action}" + (f"（{e.detail}）" if e.detail else ""))
    return "\n".join(lines)


def find_order_markdown(
    db: Session,
    project_id: int | None = None,
    order_no: str = "",
    building: str = "",
    floor: str = "",
) -> str:
    """按工单号或位置查工单，返回 Markdown 描述；未命中给出引导话术。"""
    query = db.query(WorkOrder)
    if project_id is not None:
        query = query.filter(WorkOrder.project_id == project_id)

    order = None
    if order_no:
        order = query.filter(WorkOrder.order_no == order_no.strip()).first()
    elif building or floor:
        if building and building[-1:] not in ("号", "楼", "栋"):
            building = f"{building}号楼"
        if building:
            query = query.filter(WorkOrder.building.like(f"%{building}%"))
        if floor and floor[-1:] != "层":
            floor = f"{floor}层"
        if floor:
            query = query.filter(WorkOrder.floor.like(f"%{floor}%"))
        order = query.order_by(WorkOrder.created_at.desc()).first()

    if not order:
        return "未找到匹配的工单。请提供工单编号（如 ZA-20260926-001），或说明位置（如：3号楼12层的隐患进度）。"
    return _order_markdown(db, order)


def progress_from_msg(db: Session, msg: str, project_id: int | None = None) -> str:
    """规则链路入口：从用户原话中正则解析工单号/楼栋/楼层再查询。"""
    m = _ORDER_NO_RE.search(msg)
    bm = _BUILDING_RE.search(msg)
    fm = _FLOOR_RE.search(msg)
    return find_order_markdown(
        db,
        project_id,
        order_no=m.group(0) if m else "",
        building=bm.group(1) if bm else "",
        floor=fm.group(0).replace(" ", "") if fm else "",
    )


def stats_markdown(db: Session, project_id: int | None = None) -> str:
    scope = db.query(WorkOrder)
    if project_id is not None:
        scope = scope.filter(WorkOrder.project_id == project_id)
    total = scope.count()
    closed = scope.filter(WorkOrder.status == "closed").count()
    open_orders = scope.filter(WorkOrder.status.in_(("pending_review", "dispatched", "rectifying", "recheck"))).all()
    overdue = [o for o in open_orders if o.overdue]
    risk_open = dict(Counter(o.risk_level for o in open_orders))
    lines = [
        "**当前隐患治理概况**",
        f"- 累计工单 {total} 份，已闭环 {closed} 份，整改率 **{closed / total * 100:.1f}%**" if total else "- 暂无工单数据",
        f"- 在办工单 {len(open_orders)} 份（" + "、".join(f"{k}{v}" for k, v in risk_open.items()) + "）",
        f"- 超期未闭环 **{len(overdue)}** 份" + ("，建议优先督办" if overdue else ""),
    ]
    if overdue:
        for o in overdue[:5]:
            lines.append(f"  - {o.order_no} {o.title}（{o.risk_level}风险｜{o.responsible_user.name if o.responsible_user else '未指定'}）")
    return "\n".join(lines)


def kb_answer(db: Session, msg: str) -> tuple[str, list[dict]]:
    """规范问答：向量/关键词检索 + LLM 组织回答，均有兜底。"""
    regs = kb_search(db, msg, k=3)
    logger.info("知识库检索 命中=%d", len(regs))
    refs = [
        {"doc_name": r["doc_name"], "clause_no": r["clause_no"], "title": r["title"]}
        for r in regs
    ]
    if not regs:
        return "当前知识库未检索到足够依据，建议咨询项目安全总监或补充更具体的问题。", []
    if llm_ready():
        ctx = "\n".join(f"《{r['doc_name']}》{r['clause_no']} {r['title']}：{r['content']}" for r in regs)
        answer = chat_text(
            "你是建筑工地安全知识助手，依据给定条款回答问题，并标注条款出处；检索不到的内容明确说明。120字以内。",
            f"问题：{msg}\n检索条款：\n{ctx}",
        )
        if answer:
            return answer, refs
    lines = ["根据安全知识库检索，相关要求如下：", ""]
    for i, r in enumerate(regs, 1):
        lines.append(f"{i}. 《{r['doc_name']}》{r['clause_no']}（{r['title']}）：{r['content']}")
    lines.append("")
    lines.append("建议按上述条款组织落实；如需生成整改工单，请到「隐患上报」页面提交。")
    return "\n".join(lines), refs
