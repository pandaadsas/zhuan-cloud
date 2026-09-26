from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..auth import require_roles
from ..database import get_db
from ..models import User, WeeklyReport
from ..schemas import WeeklyGenIn
from ..services.exporter import weekly_to_docx
from ..services.weekly import generate_weekly, week_range

router = APIRouter(prefix="/api/weekly", tags=["weekly"])


@router.post("/generate")
def generate(
    payload: WeeklyGenIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("safety_officer", "safety_supervisor", "project_manager")),
):
    start, end = week_range(payload.offset)
    report = generate_weekly(db, start, end, user)
    return {"id": report.id, "week": f"{start} ~ {end}", "content_md": report.content_md}


@router.get("")
def list_weekly(db: Session = Depends(get_db), user: User = Depends(require_roles("safety_officer", "safety_supervisor", "project_manager"))):
    reports = db.query(WeeklyReport).order_by(WeeklyReport.created_at.desc()).limit(10).all()
    return {
        "reports": [
            {
                "id": r.id,
                "week": f"{r.week_start} ~ {r.week_end}",
                "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
                "preview": r.content_md[:120],
            }
            for r in reports
        ]
    }


@router.get("/{report_id}/export")
def export(report_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("safety_officer", "safety_supervisor", "project_manager"))):
    report = db.get(WeeklyReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="周报不存在")
    content = weekly_to_docx(report)
    filename = f"zhuan_weekly_{report.week_start}_{report.week_end}.docx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
