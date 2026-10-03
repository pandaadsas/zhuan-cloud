"""对话查询工具：Agent 工具执行体 + 规则降级链路共用的查询与组装逻辑。"""
import logging
import re
from collections import Counter

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import OrderEvent, WorkOrder, Zone
from ..rag.retriever import search as kb_search
from ..rag.evidence import check_evidence, enabled as evidence_enabled, evidence_artifact, render_evidence
from ..serializers import STATUS_LABELS
from .llm import chat_text, llm_ready

logger = logging.getLogger("zhuan.tools")

_BUILDING_RE = re.compile(r"(\d{1,2})\s*[#号楼栋]")
_FLOOR_RE = re.compile(r"(B\d{1,2}|负?\d{1,2})\s*层")
_ORDER_NO_RE = re.compile(r"ZA-\d{8}-\d{3}")


def fallback_conversation(msg: str) -> str | None:
    """仅在模型不可用时完整匹配基本交流；正常模式由模型自主路由。"""
    text = re.sub(r"[\s，,。.!！?？、；;：:]", "", msg).lower()
    greeting = r"(?:你好|您好|嗨|哈喽|hello|hi|早上好|下午好|晚上好)"
    if re.fullmatch(rf"{greeting}+(?:啊|呀)?|{greeting}*(?:请问)?(?:你是谁|你叫什么名字|你能做什么|你有什么功能|如何上报隐患|怎么上报隐患)", text):
        return "你好，我是筑安云 AI 安全助手，可以协助查询工单、治理统计、安全规范和周报。上报隐患时，请描述位置和现场情况；可用操作取决于你的角色权限。"
    if re.fullmatch(r"谢谢你?|多谢|好的|收到|明白了|再见|拜拜", text):
        return "好的，有需要可以继续问我。"
    return None


def classify(msg: str) -> str:
    """规则意图分类：规则降级链路使用（Agent 模式下由 LLM 自主决策）。"""
    if any(k in msg for k in ("周报", "汇总一份", "安全情况汇总", "本周安全")):
        return "weekly"
    if _ORDER_NO_RE.search(msg) or any(
        k in msg for k in ("进度", "到哪一步", "处理到哪", "工单状态", "整改完了吗")
    ):
        return "progress"
    if any(k in msg for k in ("统计", "几单", "整改率", "超期")) or (
        any(k in msg for k in ("工单", "待整改", "待审核", "闭环"))
        and any(k in msg for k in ("多少", "几条", "分布", "情况"))
    ):
        return "stats"
    if re.search(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])", msg) or any(
        k in msg for k in ("规范", "条款", "临边", "防护栏", "脚手架", "动火", "有限空间", "气体检测", "高处作业", "安全带", "安全帽", "施工用电", "消防", "洞口")
    ):
        return "kb"
    return "clarify"


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


def _legacy_kb_answer(db: Session, msg: str) -> tuple[str, list[dict]]:
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


def kb_response(db: Session, msg: str, history: list[dict] | None = None) -> tuple[str, list[dict], dict]:
    if not evidence_enabled():
        reply, refs = _legacy_kb_answer(db, msg)
        return reply, refs, {"type": "clause_refs", "title": "规范依据", "data": {"refs": refs}}
    regs = kb_search(db, msg, k=3)
    evidence = check_evidence(msg, regs, query=msg, history=history)
    # 规则降级直接渲染核验要点/原文，不再追加一次可能绕过拒答的生成。
    return render_evidence(evidence), evidence["accepted_refs"], evidence_artifact(evidence)


def kb_answer(db: Session, msg: str) -> tuple[str, list[dict]]:
    reply, refs, _ = kb_response(db, msg)
    return reply, refs


# ---------- 能力面扩展：工单筛选 / 全量统计 / 站点目录 / 周报查询 / 隐患上报 ----------


def orders_list_markdown(
    db: Session,
    user,
    project_id: int | None = None,
    status: str = "",
    risk: str = "",
    keyword: str = "",
    mine: bool = False,
) -> str:
    """按状态/风险/关键词筛选工单列表；responsible 角色强制只看本人负责的。"""
    from ..routers.orders import sweep_overdue

    sweep_overdue(db)
    query = db.query(WorkOrder)
    if project_id is not None:
        query = query.filter(WorkOrder.project_id == project_id)
    if user.role == "responsible" or mine:
        query = query.filter(WorkOrder.responsible_user_id == user.id)
    if status:
        query = query.filter(WorkOrder.status == status)
    if risk:
        query = query.filter(WorkOrder.risk_level == risk)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(WorkOrder.title.like(like), WorkOrder.description.like(like)))
    rows = query.order_by(WorkOrder.created_at.desc()).limit(8).all()

    if not rows:
        return "没有符合条件的工单。"
    lines = [f"**符合条件的工单（最近 {len(rows)} 条）**"]
    for o in rows:
        lines.append(
            f"- **{o.order_no}**｜{o.title}\n"
            f"  状态：{STATUS_LABELS.get(o.status, o.status)}｜风险：{o.risk_level}｜"
            f"责任人：{o.responsible_user.name if o.responsible_user else '未指定'}｜"
            f"期限：{o.deadline.strftime('%m-%d') if o.deadline else '未设定'}"
            + ("｜⚠️已超期" if o.overdue else "")
        )
    return "\n".join(lines)


def stats_overview(db: Session, project) -> dict:
    """全量统计（汇总/分布/8周趋势/超期明细），裁剪掉对对话无意义的 meta 字段。"""
    from ..routers.stats import overview_data

    data = overview_data(db, project)
    data.pop("meta", None)
    return data


def site_directory(db: Session, project_id: int | None, kind: str) -> str:
    """区域/分包/责任人三类目录查询。"""
    from ..models import Subcontractor

    if kind == "zones":
        query = db.query(Zone)
        if project_id is not None:
            query = query.filter(Zone.project_id == project_id)
        zones = query.order_by(Zone.id).all()
        if not zones:
            return "当前项目暂无责任区域数据。"
        lines = ["**责任区域目录**"]
        for z in zones:
            lines.append(
                f"- {z.name}（{z.zone_type or '未分类'}，{z.floor_count or '?'}层）｜"
                f"责任人：{z.responsible_user.name if z.responsible_user else '未指定'}｜"
                f"分包：{z.subcontractor.name if z.subcontractor else '无'}｜当前阶段：{z.current_stage or '-'}"
            )
        return "\n".join(lines)

    if kind == "subcontractors":
        query = db.query(Subcontractor)
        if project_id is not None:
            query = query.filter(Subcontractor.project_id == project_id)
        subs = query.order_by(Subcontractor.id).all()
        if not subs:
            return "当前项目暂无分包单位数据。"
        lines = ["**分包单位目录**"]
        for s in subs:
            lines.append(f"- {s.name}｜承包范围：{s.scope or '-'}｜负责人：{s.leader_name or '-'}（{s.leader_phone or '-'}）")
        return "\n".join(lines)

    if kind == "responsible":
        from ..models import User as U

        query = db.query(U).filter(U.role == "responsible")
        if project_id is not None:
            from ..models import Subcontractor

            sub_ids = [s.id for s in db.query(Subcontractor.id).filter(Subcontractor.project_id == project_id)]
            query = query.filter(or_(U.subcontractor_id.in_(sub_ids), U.subcontractor_id.is_(None)))
        users = query.order_by(U.id).all()
        if not users:
            return "当前项目暂无分包负责人数据。"
        lines = ["**分包负责人目录**"]
        for u in users:
            sub = u.subcontractor.name if u.subcontractor_id else ""
            lines.append(f"- {u.name}" + (f"（{sub}）" if sub else "") + (f"｜电话：{u.phone}" if u.phone else ""))
        return "\n".join(lines)

    return f"未知的目录类型 {kind}，可选：zones（责任区域）/ subcontractors（分包单位）/ responsible（分包负责人）。"


def weekly_list(db: Session, project_id: int | None) -> str:
    """历史周报列表（最近 10 篇）。"""
    from ..models import WeeklyReport

    query = db.query(WeeklyReport)
    if project_id is not None:
        query = query.filter(WeeklyReport.project_id == project_id)
    rows = query.order_by(WeeklyReport.week_start.desc()).limit(10).all()
    if not rows:
        return "当前项目还没有历史周报，可以让我帮你生成一份。"
    lines = ["**历史周报（最近 %d 篇）**" % len(rows)]
    for r in rows:
        preview = (r.content_md or "").replace("\n", " ")[:60]
        lines.append(f"- {r.week_start.strftime('%Y-%m-%d')} ~ {r.week_end.strftime('%m-%d')}｜{preview}…")
    return "\n".join(lines)


def weekly_get_md(db: Session, project_id: int | None, offset: int = 0) -> str | None:
    """按周偏移取周报全文；该周未生成过则返回 None。"""
    from ..models import WeeklyReport
    from ..services.weekly import week_range

    start, _end = week_range(offset)
    query = db.query(WeeklyReport).filter(WeeklyReport.week_start == start)
    if project_id is not None:
        query = query.filter(WeeklyReport.project_id == project_id)
    report = query.order_by(WeeklyReport.id.desc()).first()
    return report.content_md if report else None


def submit_hazard(db, user, project, text: str) -> tuple[dict, list[dict]]:
    """对话内提交隐患上报：跑流水线并落库，返回结果 + 条款引用。"""
    from ..services.reporting import create_report_with_draft

    text = (text or "").strip()
    if len(text) < 5:
        return (
            {"error": "描述太短，请把隐患的位置和问题说清楚，例如：3号楼12层临边防护栏杆缺失"},
            [],
        )
    result = create_report_with_draft(db, user, project, text, "text")
    if result["need_clarify"]:
        return (
            {"need_clarify": True, "question": result["question"], "extracted": result["extracted"]},
            [],
        )
    order = result["order"]
    refs = (order.get("regulation_refs") or [])[:4]
    payload = {
        "submitted": True,
        "order_no": order["order_no"],
        "title": order["title"],
        "risk_level": order["risk_level"],
        "status": "pending_review（待安全员审核）",
        "responsible": order.get("responsible_name") or "未指定",
        "deadline": order.get("deadline", ""),
        "match_reason": result["match_reason"],
        "alternates": result["alternates"],
        "note": "提醒用户：工单已生成、待安全员在整改工单页审核派单。",
    }
    return payload, refs
