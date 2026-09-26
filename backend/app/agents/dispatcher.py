"""责任匹配：隐患位置 -> 责任分区；隐患类型 -> 分包承包范围 -> 责任人。"""
from sqlalchemy.orm import Session

from ..models import Subcontractor, User, Zone
from .extractor import SCOPE_KEYWORDS


def match_responsible(db: Session, extracted: dict) -> dict:
    """返回 {primary_user_id, primary_name, reason, alternates}，无匹配时由安全员手动指定。"""
    building = extracted.get("building", "") or ""
    hazard_type = extracted.get("hazard_type", "") or ""

    zone = None
    if building:
        zone = db.query(Zone).filter(Zone.name.like(f"%{building}%")).first()

    scope_kw = SCOPE_KEYWORDS.get(hazard_type, "")
    sub = None
    if scope_kw:
        sub = db.query(Subcontractor).filter(Subcontractor.scope.like(f"%{scope_kw}%")).first()

    primary: User | None = None
    reason = ""
    if zone and zone.responsible_user_id:
        primary = db.get(User, zone.responsible_user_id)
        if primary:
            sub_name = sub.name if sub else (zone.subcontractor.name if zone.subcontractor else "项目")
            reason = f"「{building}」属{sub_name}责任区，区域责任人为{primary.name}"
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
    candidates = db.query(User).filter(User.role == "responsible").all()
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
