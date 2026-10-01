import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..deps import current_project
from ..models import OrderEvent, Project, User, WorkOrder
from ..schemas import ActionIn
from ..serializers import event_to_dict, order_to_dict

logger = logging.getLogger("zhuan.orders")
router = APIRouter(prefix="/api/orders", tags=["orders"])

OPEN_STATUSES = ("pending_review", "dispatched", "rectifying", "recheck")


def sweep_overdue(db: Session) -> int:
    n = (
        db.query(WorkOrder)
        .filter(
            WorkOrder.status.in_(OPEN_STATUSES),
            WorkOrder.overdue.is_(False),
            WorkOrder.deadline.isnot(None),
            WorkOrder.deadline < datetime.now(),
        )
        .update({WorkOrder.overdue: True}, synchronize_session=False)
    )
    db.commit()
    if n:
        logger.info("超期巡检：%d 个工单被标记为超期", n)
    return n


def _get_order_checked(db: Session, order_id: int, user: User) -> WorkOrder:
    o = db.get(WorkOrder, order_id)
    if not o:
        raise HTTPException(status_code=404, detail="工单不存在")
    if user.role == "responsible" and o.responsible_user_id != user.id:
        raise HTTPException(status_code=403, detail="只能查看本人负责的工单")
    return o


@router.get("")
def list_orders(
    status: str = "",
    risk: str = "",
    q: str = "",
    mine: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    sweep_overdue(db)
    query = db.query(WorkOrder).filter(WorkOrder.project_id == project.id)
    if user.role == "responsible" or mine:
        query = query.filter(WorkOrder.responsible_user_id == user.id)
    if status:
        query = query.filter(WorkOrder.status == status)
    if risk:
        query = query.filter(WorkOrder.risk_level == risk)
    if q:
        query = query.filter(
            or_(
                WorkOrder.title.like(f"%{q}%"),
                WorkOrder.order_no.like(f"%{q}%"),
                WorkOrder.description.like(f"%{q}%"),
            )
        )
    orders = query.order_by(WorkOrder.created_at.desc()).limit(200).all()
    return {"orders": [order_to_dict(o, brief=True) for o in orders]}


@router.get("/{order_id}")
def order_detail(
    order_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    o = _get_order_checked(db, order_id, user)
    if o.project_id != project.id:
        raise HTTPException(status_code=404, detail="工单不存在")
    events = (
        db.query(OrderEvent)
        .filter(OrderEvent.order_id == o.id)
        .order_by(OrderEvent.created_at.asc())
        .all()
    )
    return {"order": order_to_dict(o), "events": [event_to_dict(e) for e in events]}


@router.post("/{order_id}/action")
def order_action(
    order_id: int,
    payload: ActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    o = _get_order_checked(db, order_id, user)
    action = payload.action
    now = datetime.now()
    note = (payload.note or "").strip()

    def ensure(cond: bool, msg: str):
        if not cond:
            raise HTTPException(status_code=400, detail=msg)

    if action == "approve":
        ensure(o.status == "pending_review", "当前状态不可审核")
        if o.risk_level == "重大":
            ensure(user.role == "safety_supervisor", "重大风险工单须由安全总监复核后派单")
        else:
            ensure(user.role in ("safety_officer", "safety_supervisor"), "仅安全员/安全总监可审核工单")
        resp_id = payload.responsible_user_id or o.responsible_user_id
        ensure(resp_id, "请先指定责任人")
        resp = db.get(User, resp_id)
        o.responsible_user_id = resp_id
        o.reviewer_id = user.id
        o.status = "dispatched"
        o.dispatched_at = now
        sub = resp.subcontractor.name if resp.subcontractor_id and resp.subcontractor else ""
        detail = f"工单派发至 {resp.name}" + (f"（{sub}）" if sub else "") + (f"；备注：{note}" if note else "")
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="审核通过·派单", detail=detail))

    elif action == "reject":
        ensure(o.status == "pending_review", "当前状态不可驳回")
        ensure(user.role in ("safety_officer", "safety_supervisor"), "仅安全员/安全总监可驳回工单")
        o.reviewer_id = user.id
        o.status = "rejected"
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="驳回工单", detail=note or "信息不完整，需重新核实"))

    elif action == "start":
        ensure(o.status == "dispatched", "当前状态不可开始整改")
        ensure(user.id == o.responsible_user_id, "仅责任人可开始整改")
        o.status = "rectifying"
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="开始整改", detail=note or "接收工单，组织班组整改"))

    elif action == "submit":
        ensure(o.status == "rectifying", "当前状态不可提交复查")
        ensure(user.id == o.responsible_user_id, "仅责任人可提交复查")
        o.status = "recheck"
        o.rect_note = note or "已完成整改"
        o.rect_images = payload.images or []
        n = len(o.rect_images)
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="提交复查",
                          detail=o.rect_note + (f"（附整改照片{n}张）" if n else "")))

    elif action == "pass":
        ensure(o.status == "recheck", "当前状态不可闭环")
        ensure(user.role in ("safety_officer", "safety_supervisor"), "仅安全员/安全总监可复查闭环")
        o.status = "closed"
        o.closed_at = now
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="复查合格·闭环", detail=note or "现场复查符合要求，工单闭环"))

    elif action == "fail_recheck":
        ensure(o.status == "recheck", "当前状态不可退回")
        ensure(user.role in ("safety_officer", "safety_supervisor"), "仅安全员/安全总监可退回复查")
        o.status = "rectifying"
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="复查不合格·退回整改", detail=note or "整改不到位，请继续整改"))

    elif action == "extend":
        ensure(user.role in ("safety_officer", "safety_supervisor"), "仅安全员/安全总监可延期")
        ensure(o.status in ("dispatched", "rectifying"), "当前状态不可延期")
        o.deadline = (o.deadline or now) + timedelta(days=2)
        o.overdue = False
        db.add(OrderEvent(order_id=o.id, actor=user.name, action="整改延期", detail=f"期限调整为 {o.deadline:%m-%d %H:%M}" + (f"；原因：{note}" if note else "")))

    else:
        raise HTTPException(status_code=400, detail="未知操作")

    o.updated_at = now
    db.commit()
    db.refresh(o)
    logger.info("工单操作 order=%s action=%s operator=%s(%s) -> status=%s",
                o.order_no, action, user.name, user.role, o.status)
    return {"order": order_to_dict(o)}
