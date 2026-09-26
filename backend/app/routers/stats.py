from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import db_mode, get_db
from ..models import User, WorkOrder
from ..agents.llm import llm_ready
from .orders import sweep_overdue

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sweep_overdue(db)
    total = db.query(WorkOrder).count()
    closed = db.query(WorkOrder).filter(WorkOrder.status == "closed").count()
    open_orders = db.query(WorkOrder).filter(
        WorkOrder.status.in_(("pending_review", "dispatched", "rectifying", "recheck"))
    ).all()
    status_counts = dict(Counter(o.status for o in db.query(WorkOrder).all()))
    overdue = sorted([o for o in open_orders if o.overdue], key=lambda o: (o.deadline or datetime.now()))

    today_start = datetime.combine(datetime.now().date(), datetime.min.time())
    today_new = db.query(WorkOrder).filter(WorkOrder.created_at >= today_start).count()

    trend = []
    monday = datetime.now().date() - timedelta(days=datetime.now().date().weekday())
    for i in range(7, -1, -1):
        ws = monday - timedelta(weeks=i)
        we = ws + timedelta(days=7)
        ws_dt = datetime.combine(ws, datetime.min.time())
        we_dt = datetime.combine(we, datetime.min.time())
        new = db.query(WorkOrder).filter(WorkOrder.created_at >= ws_dt, WorkOrder.created_at < we_dt).count()
        done = db.query(WorkOrder).filter(WorkOrder.closed_at.isnot(None), WorkOrder.closed_at >= ws_dt, WorkOrder.closed_at < we_dt).count()
        trend.append({"label": f"{ws.month}/{ws.day}", "new": new, "closed": done})

    return {
        "total": total,
        "closed": closed,
        "rect_rate": f"{closed / total * 100:.1f}%" if total else "0%",
        "today_new": today_new,
        "open_total": len(open_orders),
        "open_risk_counts": dict(Counter(o.risk_level for o in open_orders)),
        "status_counts": status_counts,
        "type_top": dict(Counter(o.hazard_type for o in db.query(WorkOrder).all()).most_common(6)),
        "overdue": [
            {
                "order_no": o.order_no,
                "title": o.title,
                "risk_level": o.risk_level,
                "responsible": o.responsible_user.name if o.responsible_user else "未指定",
                "deadline": o.deadline.strftime("%m-%d") if o.deadline else "",
            }
            for o in overdue[:10]
        ],
        "trend": trend,
        "meta": {
            "db_mode": db_mode(),
            "ai_engine": "通义千问" if llm_ready() else "",
        },
    }
