"""责任匹配：隐患位置 -> 责任分区；隐患类型 -> 分包承包范围 -> 责任人。"""
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import Subcontractor, User, Zone
from .extractor import SCOPE_KEYWORDS


def match_responsible(db: Session, extracted: dict, project_id: int | None = None) -> dict:
    """返回 {primary_user_id, primary_name, reason, alternates}，无匹配时由安全员手动指定。

    project_id 提供时只在该项目内匹配区域和分包单位。
    """
    building = extracted.get("building", "") or ""
    hazard_type = extracted.get("hazard_type", "") or ""

    zone = None
    if building:
        query = db.query(Zone).filter(Zone.name.like(f"%{building}%"))
        if project_id is not None:
            query = query.filter(Zone.project_id == project_id)
        zone = query.first()

    scope_kw = SCOPE_KEYWORDS.get(hazard_type, "")
    sub = None
    if scope_kw:
        query = db.query(Subcontractor).filter(Subcontractor.scope.like(f"%{scope_kw}%"))
        if project_id is not None:
            query = query.filter(Subcontractor.project_id == project_id)
        sub = query.first()

    primary: User | None = None
    reason = ""
    if zone and zone.responsible_user_id:
        primary = db.get(User, zone.responsible_user_id)
        if primary:
            zone_sub = zone.subcontractor.name if zone.subcontractor else (sub.name if sub else "项目")
            reason = f"「{building}」属{zone_sub}责任区，区域责任人为{primary.name}"
    elif sub:
        primary = (
            db.query(User)
            .filter(User.subcontractor_id == sub.id, User.role == "responsible")
            .first()
        )
        if primary:
            reason = f"隐患类型「{hazard_type}」属{sub.name}承包范围（{scope_kw}），匹配负责人{primary.name}"

    if not primary:
        reason = "未自动匹配到责任人，请安全员在审核时手动指定"

    alternates = []
    candidate_query = db.query(User).filter(User.role == "responsible")
    if project_id is not None:
        # 候选责任人限定为该项目分包下的人员（未挂分包的全局责任人保留）
        proj_sub_ids = db.query(Subcontractor.id).filter(Subcontractor.project_id == project_id)
        candidate_query = candidate_query.filter(
            or_(User.subcontractor_id.in_(proj_sub_ids), User.subcontractor_id.is_(None))
        )
    candidates = candidate_query.all()
    for u in candidates:
        if primary and u.id == primary.id:
            continue
        score = 0.5
        if sub and u.subcontractor_id == sub.id:
            score = 0.7
        sub_name = u.subcontractor.name if u.subcontractor_id else ""
        alternates.append({"user_id": u.id, "name": u.name, "subcontractor": sub_name, "score": score})
    alternates.sort(key=lambda x: -x["score"])

    return {
        "primary_user_id": primary.id if primary else None,
        "primary_name": primary.name if primary else "",
        "reason": reason,
        "alternates": alternates[:2],
    }
