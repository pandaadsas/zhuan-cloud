from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents.extractor import HAZARD_RULES
from ..agents.llm import llm_ready
from ..auth import get_current_user
from ..config import settings
from ..database import db_mode, get_db
from ..deps import current_project
from ..models import Project, Subcontractor, User, Zone
from ..serializers import STATUS_LABELS

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/options")
def options(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    zones = db.query(Zone).filter(Zone.project_id == project.id).all()
    resp_users = db.query(User).filter(User.role == "responsible").all()
    return {
        "zones": [
            {
                "id": z.id,
                "name": z.name,
                "current_stage": z.current_stage,
                "responsible_name": z.responsible_user.name if z.responsible_user else "",
            }
            for z in zones
        ],
        "responsible_users": [
            {
                "id": u.id,
                "name": u.name,
                "subcontractor": u.subcontractor.name if u.subcontractor_id and u.subcontractor else "",
            }
            for u in resp_users
        ],
        "hazard_types": sorted({t for _, t, _ in HAZARD_RULES} | {"其他-待归类"}),
        "risk_levels": ["低", "中", "高", "重大"],
        "statuses": STATUS_LABELS,
    }


@router.get("/subcontractors")
def subcontractors(db: Session = Depends(get_db)):
    """公开接口：注册页选择分包单位用。"""
    subs = db.query(Subcontractor).all()
    return [{"id": s.id, "name": s.name} for s in subs]


@router.get("/info")
def info(
    db: Session = Depends(get_db),
    project: Project = Depends(current_project),
):
    return {
        "app": "筑安云",
        "slogan": "把案头交给AI，把安全留给现场",
        "project": {
            "id": project.id,
            "name": project.name,
            "location": project.location,
            "scale_desc": project.scale_desc,
            "current_stage": project.current_stage,
        },
        "db_mode": db_mode(),
        "mock_mode": settings.mock_mode,
        "ai_engine": "通义千问" if llm_ready() else "",
    }
