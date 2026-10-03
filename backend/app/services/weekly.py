"""按风险等级汇总安全周报：统计采集 + AI叙述生成（模拟模式走模板引擎）。"""
import logging
from collections import Counter
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from ..agents.llm import chat_text
from ..deps import get_current_project
from ..models import User, WeeklyReport, WorkOrder

logger = logging.getLogger("zhuan.weekly")

OPEN_STATUSES = ("pending_review", "dispatched", "rectifying", "recheck")

WEEKLY_SYSTEM_PROMPT = """你是项目安全总监助理，撰写周安全例会用的隐患治理周报。基于给定的JSON统计数据撰写，
包含四个部分（用中文序号）：
一、本周隐患概况（总数、按风险等级分布、按类型Top3）
二、整改进展（已闭环数、整改率、超期情况）
三、重点关注（高/重大风险隐患和超期工单，逐条点出）
四、下周管理建议（2-3条，针对数据反映的趋势）
只使用统计数据中出现的数字，不要编造。使用Markdown，## 作小节标题。"""


def week_range(offset: int = 0) -> tuple[date, date]:
    """offset=0 本周一~今天，-1 上周一~上周日。"""
    today = date.today()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    if offset == 0:
        return monday, today
    return monday, monday + timedelta(days=6)


def collect_stats(db: Session, start: date, end: date) -> dict:
    week_start_dt = datetime.combine(start, datetime.min.time())
    week_end_dt = datetime.combine(end + timedelta(days=1), datetime.min.time())

    new_orders = (
        db.query(WorkOrder)
        .filter(WorkOrder.created_at >= week_start_dt, WorkOrder.created_at < week_end_dt)
        .all()
    )
    open_orders = db.query(WorkOrder).filter(WorkOrder.status.in_(OPEN_STATUSES)).all()
    total = db.query(WorkOrder).count()
    closed_total = db.query(WorkOrder).filter(WorkOrder.status == "closed").count()

    overdue = [
        {
            "order_no": o.order_no,
            "title": o.title,
            "risk_level": o.risk_level,
            "responsible": o.responsible_user.name if o.responsible_user else "未指定",
            "deadline": o.deadline.strftime("%m-%d") if o.deadline else "",
        }
        for o in open_orders
        if o.overdue
    ]

    return {
        "week": f"{start.isoformat()} ~ {end.isoformat()}",
        "new_total": len(new_orders),
        "new_by_risk": dict(Counter(o.risk_level for o in new_orders)),
        "new_by_type": dict(Counter(o.hazard_type for o in new_orders).most_common(5)),
        "closed_in_week": db.query(WorkOrder).filter(
            WorkOrder.status == "closed",
            WorkOrder.closed_at >= week_start_dt,
            WorkOrder.closed_at < week_end_dt,
        ).count(),
        "open_total": len(open_orders),
        "open_by_risk": dict(Counter(o.risk_level for o in open_orders)),
        "rect_rate": f"{(closed_total / total * 100):.1f}%" if total else "0%",
        "overdue": overdue[:10],
        "overdue_total": len(overdue),
        "notable": [
            {
                "order_no": o.order_no,
                "title": o.title,
                "risk_level": o.risk_level,
                "status": o.status,
                "responsible": o.responsible_user.name if o.responsible_user else "未指定",
            }
            for o in new_orders
            if o.risk_level in ("高", "重大")
        ][:8],
    }


def _template_md(s: dict) -> str:
    lines = [f"# 筑安云·项目安全周报（{s['week']}）", ""]
    lines.append("## 一、本周隐患概况")
    lines.append(
        f"- 本周新增隐患工单 **{s['new_total']}** 份，风险分布："
        + "、".join(f"{k}{v}份" for k, v in sorted(s["new_by_risk"].items(), key=lambda x: -x[1]))
    )
    if s["new_by_type"]:
        lines.append(
            "- 隐患类型集中："
            + "、".join(f"{k}({v})" for k, v in list(s["new_by_type"].items())[:3])
        )
    lines.append("")
    lines.append("## 二、整改进展")
    lines.append(f"- 本周闭环 **{s['closed_in_week']}** 份，累计整改率 **{s['rect_rate']}**")
    lines.append(f"- 当前在办工单 {s['open_total']} 份（" + "、".join(f"{k}{v}" for k, v in s["open_by_risk"].items()) + "）")
    lines.append(f"- 超期未闭环 **{s['overdue_total']}** 份" + ("，需重点督办" if s["overdue_total"] else ""))
    lines.append("")
    lines.append("## 三、重点关注")
    if s["overdue"]:
        for o in s["overdue"][:5]:
            lines.append(f"- 【超期】{o['order_no']} {o['title']}（{o['risk_level']}风险，责任人：{o['responsible']}，期限{o['deadline']}）")
    for o in s["notable"][:5]:
        lines.append(f"- 【{o['risk_level']}风险】{o['order_no']} {o['title']}（当前状态：{o['status']}，责任人：{o['responsible']}）")
    if not s["overdue"] and not s["notable"]:
        lines.append("- 本周无高等级风险及超期工单")
    lines.append("")
    lines.append("## 四、下周管理建议")
    if s["overdue_total"] > 0:
        lines.append("- 建议对超期工单启动约谈机制，由安全总监组织专项督办")
    if any("高处作业" in t for t in s["new_by_type"]):
        lines.append("- 高处作业类隐患占比高，建议开展临边洞口防护专项检查")
    if any("消防" in t for t in s["new_by_type"]):
        lines.append("- 消防安全隐患反复出现，建议纳入每日班前检查清单")
    lines.append("- 持续用好筑安云随手拍上报，保持隐患排查频次，重点区域加密巡查")
    return "\n".join(lines)


def generate_weekly(db: Session, start: date, end: date, creator: User, project_id: int | None = None) -> WeeklyReport:
    stats = collect_stats(db, start, end)
    md = chat_text(WEEKLY_SYSTEM_PROMPT, "统计数据JSON：\n" + str(stats))
    if not md:
        md = _template_md(stats)
    md = md + f"\n\n---\n*筑安云AI自动生成｜{datetime.now():%Y-%m-%d %H:%M}*"
    report = WeeklyReport(
        project_id=project_id if project_id is not None else get_current_project(db).id,
        week_start=start,
        week_end=end,
        content_md=md,
        stats_json=stats,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report
