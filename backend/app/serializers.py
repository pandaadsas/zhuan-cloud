from .models import OrderEvent, User, WorkOrder

STATUS_LABELS = {
    "pending_review": "待审核",
    "dispatched": "已派发",
    "rectifying": "整改中",
    "recheck": "待复查",
    "closed": "已闭环",
    "rejected": "已驳回",
}
ROLE_LABELS = {
    "safety_officer": "安全员",
    "safety_supervisor": "安全总监",
    "project_manager": "项目经理",
    "responsible": "分包责任人",
}


def user_public(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "name": u.name,
        "role": u.role,
        "role_label": ROLE_LABELS.get(u.role, u.role),
        "phone": u.phone,
        "subcontractor": u.subcontractor.name if u.subcontractor_id and u.subcontractor else "",
    }


def order_to_dict(o: WorkOrder, brief: bool = False) -> dict:
    d = {
        "id": o.id,
        "order_no": o.order_no,
        "title": o.title,
        "building": o.building,
        "floor": o.floor,
        "spot": o.spot,
        "hazard_type": o.hazard_type,
        "risk_level": o.risk_level,
        "status": o.status,
        "status_label": STATUS_LABELS.get(o.status, o.status),
        "overdue": o.overdue,
        "source_type": o.source_type,
        "deadline": o.deadline.strftime("%Y-%m-%d %H:%M") if o.deadline else None,
        "created_at": o.created_at.strftime("%Y-%m-%d %H:%M"),
        "responsible_user_id": o.responsible_user_id,
        "responsible_name": o.responsible_user.name if o.responsible_user else "",
        "responsible_sub": (
            o.responsible_user.subcontractor.name
            if o.responsible_user and o.responsible_user.subcontractor
            else ""
        ),
    }
    if not brief:
        d.update(
            {
                "description": o.description,
                "suggestion": o.suggestion,
                "regulation_refs": o.regulation_refs or [],
                "rect_note": o.rect_note,
                "dispatched_at": o.dispatched_at.strftime("%Y-%m-%d %H:%M") if o.dispatched_at else None,
                "closed_at": o.closed_at.strftime("%Y-%m-%d %H:%M") if o.closed_at else None,
                "reviewer_name": o.reviewer.name if o.reviewer else "",
                "zone_name": o.zone.name if o.zone else "",
            }
        )
    return d


def event_to_dict(e: OrderEvent) -> dict:
    return {
        "id": e.id,
        "actor": e.actor,
        "action": e.action,
        "detail": e.detail,
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M"),
    }
