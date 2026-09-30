"""跨路由共享的请求级依赖。"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Project


def get_current_project(db: Session) -> Project:
    """取当前项目上下文。

    单项目阶段：返回唯一项目；多项目化后改为从请求上下文（header/用户归属）解析。
    """
    project = db.query(Project).order_by(Project.id).first()
    if project is None:
        raise HTTPException(status_code=500, detail="系统未初始化项目，请先运行初始化")
    return project
