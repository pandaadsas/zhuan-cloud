"""跨路由共享的请求级依赖。"""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import Project


def resolve_project(db: Session, project_id: int | None = None) -> Project:
    """按显式 id 解析项目；未指定时回退第一个项目（单项目兼容）。"""
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project
    return get_current_project(db)


def current_project(
    request: Request,
    db: Session = Depends(get_db),
) -> Project:
    """FastAPI 依赖：从 X-Project-Id 请求头解析当前项目上下文。"""
    raw = request.headers.get("X-Project-Id")
    project_id = int(raw) if raw and raw.isdigit() else None
    return resolve_project(db, project_id)


def get_current_project(db: Session) -> Project:
    """取唯一项目（单项目回退）；多项目场景请用 current_project 依赖。"""
    project = db.query(Project).order_by(Project.id).first()
    if project is None:
        raise HTTPException(status_code=500, detail="系统未初始化项目，请先创建项目")
    return project
