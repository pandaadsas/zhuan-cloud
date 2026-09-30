from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents.graph import process_report
from ..auth import get_current_user, require_roles
from ..database import get_db
from ..deps import get_current_project
from ..models import Report, User, WorkOrder, Zone
from ..schemas import ReportIn
from ..serializers import order_to_dict

router = APIRouter(prefix="/api/reports", tags=["reports"])


def gen_order_no(db: Session) -> str:
    day = datetime.now().strftime("%Y%m%d")
    base = f"ZA-{day}-"
    count = db.query(WorkOrder).filter(WorkOrder.order_no.like(f"{base}%")).count()
    return f"{base}{count + 1:03d}"


@router.post("")
def create_report(payload: ReportIn, db: Session = Depends(get_db), user: User = Depends(require_roles("safety_officer", "safety_supervisor"))):
    text = (payload.text or "").strip()
    if len(text) < 5:
        raise HTTPException(status_code=400, detail="请描述隐患内容（至少5个字），如：3号楼12层临边防护缺失")

    project = get_current_project(db)
    result = process_report(db, text, payload.input_type, project_id=project.id)
    report = Report(
        project_id=project.id,
        reporter_id=user.id,
        input_type=payload.input_type,
        raw_text=text,
        processed=not result["need_clarify"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if result["need_clarify"]:
        return {
            "need_clarify": True,
            "question": result["question"],
            "extracted": result["extracted"],
            "report_id": report.id,
        }

    draft = result["order_draft"]
    zone = None
    if draft["building"]:
        zone = (
            db.query(Zone)
            .filter(Zone.project_id == project.id, Zone.name.like(f"%{draft['building']}%"))
            .first()
        )
    order = WorkOrder(
        order_no=gen_order_no(db),
        project_id=project.id,
        report_id=report.id,
        title=draft["title"],
        building=draft["building"],
        floor=draft["floor"],
        spot=draft["spot"],
        zone_id=zone.id if zone else None,
        hazard_type=draft["hazard_type"],
        description=draft["description"],
        risk_level=draft["risk_level"],
        suggestion=draft["suggestion"],
        regulation_refs=draft["regulation_refs"],
        source_type=draft["source_type"],
        responsible_user_id=draft["responsible_user_id"],
        deadline=datetime.fromisoformat(draft["deadline"]),
        status="pending_review",
    )
    db.add(order)
    db.flush()
    from ..models import OrderEvent

    db.add(OrderEvent(order_id=order.id, actor=f"安全员 {user.name}", action="上报隐患", detail=text))
    db.add(
        OrderEvent(
            order_id=order.id,
            actor="筑安云AI",
            action="生成工单草稿",
            detail=f"抽取引擎：{draft['extraction_engine']}｜匹配条款{len(draft['regulation_refs'])}条｜{draft['match_reason']}",
        )
    )
    db.commit()
    db.refresh(order)
    return {
        "need_clarify": False,
        "order": order_to_dict(order),
        "extracted": result["extracted"],
        "regs": result["regs"],
        "alternates": draft["alternates"],
        "match_reason": draft["match_reason"],
    }


@router.get("")
def list_reports(db: Session = Depends(get_db), user: User = Depends(get_current_user), limit: int = 50):
    query = db.query(Report)
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
