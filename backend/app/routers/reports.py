import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..deps import current_project
from ..models import Project, Report, User, WorkOrder
from ..schemas import ReportIn
from ..services.reporting import create_report_with_draft

logger = logging.getLogger("zhuan.reports")
router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("")
def create_report(
    payload: ReportIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("safety_officer", "safety_supervisor")),
    project: Project = Depends(current_project),
):
    text = (payload.text or "").strip()
    if len(text) < 5:
        raise HTTPException(status_code=400, detail="请描述隐患内容（至少5个字），如：3号楼12层临边防护缺失")

    logger.info("收到隐患上报 user=%s type=%s len=%d", user.name, payload.input_type, len(text))
    return create_report_with_draft(db, user, project, text, payload.input_type)


@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
    limit: int = 50,
):
    query = db.query(Report).filter(Report.project_id == project.id)
    if user.role == "safety_officer":
        query = query.filter(Report.reporter_id == user.id)
    reports = query.order_by(Report.created_at.desc()).limit(limit).all()
    out = []
    for r in reports:
        order = db.query(WorkOrder).filter(WorkOrder.report_id == r.id).first()
        out.append(
            {
                "id": r.id,
                "input_type": r.input_type,
                "raw_text": r.raw_text,
                "processed": r.processed,
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
                "order_no": order.order_no if order else "",
                "order_status": order.status if order else "",
            }
        )
    return {"reports": out}
