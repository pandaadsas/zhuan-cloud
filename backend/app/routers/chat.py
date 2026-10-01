"""AI对话助手：进度查询 / 统计速览 / 知识库问答 / 周报生成。"""
import logging
import re
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents.llm import chat_text, llm_ready
from ..auth import get_current_user
from ..database import get_db
from ..deps import current_project
from ..models import Project, User, WorkOrder
from ..rag.retriever import search as kb_search
from ..schemas import ChatIn
from ..serializers import STATUS_LABELS
from ..services.weekly import generate_weekly, week_range

logger = logging.getLogger("zhuan.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])


def classify(msg: str) -> str:
    if any(k in msg for k in ("周报", "汇总一份", "安全情况汇总", "本周安全")):
        return "weekly"
    if re.search(r"ZA-\d{8}-\d{3}", msg) or any(
        k in msg for k in ("进度", "到哪一步", "处理到哪", "工单状态", "整改完了吗")
    ):
        return "progress"
    if any(k in msg for k in ("统计", "多少", "几单", "几份", "整改率", "超期", "分布", "情况")):
        return "stats"
    return "kb"


def handle_progress(db: Session, msg: str, project_id: int | None = None) -> tuple[str, list]:
    query = db.query(WorkOrder)
    if project_id is not None:
        query = query.filter(WorkOrder.project_id == project_id)
    m = re.search(r"ZA-\d{8}-\d{3}", msg)
    order = None
    if m:
        order = query.filter(WorkOrder.order_no == m.group(0)).first()
    else:
        bm = re.search(r"(\d{1,2})\s*[#号楼栋]", msg)
        fm = re.search(r"(B\d{1,2}|负?\d{1,2})\s*层", msg)
        if bm:
            query = query.filter(WorkOrder.building.like(f"%{bm.group(1)}号楼%"))
        if fm:
            query = query.filter(WorkOrder.floor == fm.group(0).replace(" ", ""))
        order = query.order_by(WorkOrder.created_at.desc()).first()

    if not order:
        return (
            "未找到匹配的工单。请提供工单编号（如 ZA-20260926-001），或说明位置（如：3号楼12层的隐患进度）。"
        ), []

    lines = [
        f"**{order.order_no}｜{order.title}**",
        f"- 当前状态：**{STATUS_LABELS.get(order.status, order.status)}**",
        f"- 风险等级：{order.risk_level}｜责任人：{order.responsible_user.name if order.responsible_user else '未指定'}",
        f"- 整改期限：{order.deadline.strftime('%m-%d %H:%M') if order.deadline else '未设定'}"
        + ("｜⚠️已超期" if order.overdue else ""),
    ]
    lines.append("- 最近流转：")
    from ..models import OrderEvent

    recent = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == order.id)
        .order_by(OrderEvent.created_at.desc())
        .limit(4)
        .all()
    )
    for e in reversed(recent):
        lines.append(f"  - {e.created_at.strftime('%m-%d %H:%M')} {e.actor}：{e.action}" + (f"（{e.detail}）" if e.detail else ""))
    return "\n".join(lines), []


def handle_stats(db: Session, msg: str, project_id: int | None = None) -> tuple[str, list]:
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
    return "\n".join(lines), []


def handle_kb(db: Session, msg: str) -> tuple[str, list]:
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


@router.post("")
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    msg = (payload.message or "").strip()
    if not msg:
        return {"intent": "empty", "reply": "请输入您的问题，例如：3号楼12层的隐患整改到哪一步了？"}
    intent = classify(msg)
    logger.info("AI对话 user=%s(%s) intent=%s project=%s msg=%s", user.name, user.role, intent, project.name, msg[:50])

    if intent == "weekly":
        if user.role not in ("safety_officer", "safety_supervisor", "project_manager"):
            return {
                "intent": "weekly",
                "reply": "周报生成权限为安全员/安全总监/项目经理。如需了解整改情况，可以直接问我进度或统计。",
            }
        start, end = week_range(0)
        report = generate_weekly(db, start, end, user, project_id=project.id)
        return {
            "intent": "weekly",
            "reply": report.content_md,
            "weekly_id": report.id,
            "refs": [],
        }
    if intent == "progress":
        reply, refs = handle_progress(db, msg, project_id=project.id)
        return {"intent": intent, "reply": reply, "refs": refs}
    if intent == "stats":
        reply, refs = handle_stats(db, msg, project_id=project.id)
        return {"intent": intent, "reply": reply, "refs": refs}
    reply, refs = handle_kb(db, msg)
    return {"intent": intent, "reply": reply, "refs": refs}
