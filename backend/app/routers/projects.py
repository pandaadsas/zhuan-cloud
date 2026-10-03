"""项目管理：项目/区域/分包的增改查（多项目支持）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_roles
from ..database import get_db
from ..models import Project, Subcontractor, User, WorkOrder, Zone
from ..schemas import ProjectIn, SubcontractorIn, ZoneIn

router = APIRouter(prefix="/api/projects", tags=["projects"])

MANAGE_ROLES = ("project_manager", "safety_supervisor")


def _project_dict(p: Project, zone_count: int | None = None) -> dict:
    d = {
        "id": p.id,
        "name": p.name,
        "location": p.location,
        "total_area": p.total_area,
        "scale_desc": p.scale_desc,
        "current_stage": p.current_stage,
        "note": p.note,
    }
    if zone_count is not None:
        d["zone_count"] = zone_count
    return d


def _zone_dict(z: Zone) -> dict:
    return {
        "id": z.id,
        "project_id": z.project_id,
        "name": z.name,
        "zone_type": z.zone_type,
        "floor_count": z.floor_count,
        "current_stage": z.current_stage,
        "subcontractor_id": z.subcontractor_id,
        "subcontractor": z.subcontractor.name if z.subcontractor else "",
        "responsible_user_id": z.responsible_user_id,
        "responsible_name": z.responsible_user.name if z.responsible_user else "",
    }


def _sub_dict(s: Subcontractor) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "name": s.name,
        "scope": s.scope,
        "leader_name": s.leader_name,
        "leader_phone": s.leader_phone,
    }


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    projects = db.query(Project).order_by(Project.id).all()
    return {
        "projects": [
            _project_dict(p, db.query(Zone).filter(Zone.project_id == p.id).count())
            for p in projects
        ]
    }


@router.post("")
def create_project(
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="项目名称不能为空")
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_dict(project, 0)


@router.put("/{project_id}")
def update_project(
    project_id: int,
    payload: ProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    for k, v in payload.model_dump().items():
        setattr(project, k, v)
    db.commit()
    db.refresh(project)
    return _project_dict(project)


@router.get("/{project_id}/zones")
def list_zones(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    zones = db.query(Zone).filter(Zone.project_id == project_id).order_by(Zone.id).all()
    return {"zones": [_zone_dict(z) for z in zones]}


def _check_zone_refs(db: Session, payload: ZoneIn) -> None:
    if payload.subcontractor_id is not None and db.get(Subcontractor, payload.subcontractor_id) is None:
        raise HTTPException(status_code=404, detail="分包单位不存在")
    if payload.responsible_user_id is not None and db.get(User, payload.responsible_user_id) is None:
        raise HTTPException(status_code=404, detail="责任人用户不存在")


@router.post("/{project_id}/zones")
def create_zone(
    project_id: int,
    payload: ZoneIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="区域名称不能为空")
    _check_zone_refs(db, payload)
    zone = Zone(project_id=project_id, **payload.model_dump())
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return _zone_dict(zone)


@router.put("/zones/{zone_id}")
def update_zone(
    zone_id: int,
    payload: ZoneIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="区域不存在")
    _check_zone_refs(db, payload)
    for k, v in payload.model_dump().items():
        setattr(zone, k, v)
    db.commit()
    db.refresh(zone)
    return _zone_dict(zone)


@router.delete("/zones/{zone_id}")
def delete_zone(
    zone_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="区域不存在")
    used = db.query(WorkOrder).filter(WorkOrder.zone_id == zone_id).count()
    if used:
        raise HTTPException(status_code=409, detail=f"该区域已关联 {used} 条工单，不能删除")
    db.delete(zone)
    db.commit()
    return {"deleted": zone_id}


@router.get("/{project_id}/subcontractors")
def list_project_subs(project_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    subs = db.query(Subcontractor).filter(Subcontractor.project_id == project_id).order_by(Subcontractor.id).all()
    return {"subcontractors": [_sub_dict(s) for s in subs]}


@router.post("/{project_id}/subcontractors")
def create_sub(
    project_id: int,
    payload: SubcontractorIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    if db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="分包单位名称不能为空")
    sub = Subcontractor(project_id=project_id, **payload.model_dump())
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _sub_dict(sub)


@router.put("/subcontractors/{sub_id}")
def update_sub(
    sub_id: int,
    payload: SubcontractorIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MANAGE_ROLES)),
):
    sub = db.get(Subcontractor, sub_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="分包单位不存在")
    for k, v in payload.model_dump().items():
        setattr(sub, k, v)
    db.commit()
    db.refresh(sub)
    return _sub_dict(sub)
