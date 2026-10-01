from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents.llm import llm_ready
from ..auth import get_current_user
from ..database import db_mode, get_db
from ..deps import current_project
from ..models import Project, User, WorkOrder
from .orders import sweep_overdue

router = APIRouter(prefix="/api/stats", tags=["stats"])

OPEN_STATUSES = ("pending_review", "dispatched", "rectifying", "recheck")


@router.get("/overview")
def overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    sweep_overdue(db)
    # 单查询聚合：避免对远程库多次串行往返（每次 ~0.4s）
    rows = db.query(
        WorkOrder.id,
        WorkOrder.order_no,
        WorkOrder.title,
        WorkOrder.status,
        WorkOrder.risk_level,
        WorkOrder.hazard_type,
        WorkOrder.overdue,
        WorkOrder.deadline,
        WorkOrder.created_at,
        WorkOrder.closed_at,
        WorkOrder.responsible_user_id,
    ).filter(WorkOrder.project_id == project.id).all()

    total = len(rows)
    status_counts = dict(Counter(r.status for r in rows))
    closed = status_counts.get("closed", 0)
    open_rows = [r for r in rows if r.status in OPEN_STATUSES]
    overdue_rows = sorted(
        [r for r in open_rows if r.overdue], key=lambda r: (r.deadline or datetime.now())
    )

    today_start = datetime.combine(datetime.now().date(), datetime.min.time())

    monday = (datetime.now().date() - timedelta(days=datetime.now().date().weekday()))
    week_bins = []
    for i in range(7, -1, -1):
        ws = monday - timedelta(weeks=i)
        week_bins.append((ws, ws + timedelta(days=7)))

    def week_index(dt: datetime):
        d = dt.date()
        for idx, (ws, we) in enumerate(week_bins):
            if ws <= d < we:
                return idx
        return None

    new_counts = [0] * len(week_bins)
    closed_counts = [0] * len(week_bins)
    for r in rows:
        if r.created_at:
            i = week_index(r.created_at)
            if i is not None:
                new_counts[i] += 1
        if r.closed_at:
            i = week_index(r.closed_at)
            if i is not None:
                closed_counts[i] += 1

    resp_ids = {r.responsible_user_id for r in overdue_rows if r.responsible_user_id}
    names = {}
    if resp_ids:
        names = {u.id: u.name for u in db.query(User).filter(User.id.in_(resp_ids)).all()}

    return {
        "total": total,
        "closed": closed,
        "rect_rate": f"{closed / total * 100:.1f}%" if total else "0%",
        "today_new": sum(1 for r in rows if r.created_at and r.created_at >= today_start),
        "open_total": len(open_rows),
        "open_risk_counts": dict(Counter(r.risk_level for r in open_rows)),
        "status_counts": status_counts,
        "type_top": dict(Counter(r.hazard_type for r in rows).most_common(6)),
        "overdue": [
            {
                "order_no": r.order_no,
                "title": r.title,
                "risk_level": r.risk_level,
                "responsible": names.get(r.responsible_user_id, "未指定"),
                "deadline": r.deadline.strftime("%m-%d") if r.deadline else "",
            }
            for r in overdue_rows[:10]
        ],
        "trend": [
            {"label": f"{ws.month}/{ws.day}", "new": new_counts[i], "closed": closed_counts[i]}
            for i, (ws, _we) in enumerate(week_bins)
        ],
        "meta": {
            "db_mode": db_mode(),
            "ai_engine": "通义千问" if llm_ready() else "",
        },
    }
