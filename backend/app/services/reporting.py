"""隐患上报落库：LangGraph 流水线结果 → Report + WorkOrder 草稿 + 流转事件。

reports.py 的 REST 入口与 chatbot 的 submit_hazard_report 工具共用一份，
保证工单编号生成、区域匹配、事件留痕逻辑不漂移。
"""
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ..agents.graph import process_report
from ..models import OrderEvent, Project, Report, User, WorkOrder, Zone
from ..serializers import order_to_dict

logger = logging.getLogger("zhuan.reporting")


def gen_order_no(db: Session) -> str:
    day = datetime.now().strftime("%Y%m%d")
    base = f"ZA-{day}-"
    count = db.query(WorkOrder).filter(WorkOrder.order_no.like(f"{base}%")).count()
    return f"{base}{count + 1:03d}"


def create_report_with_draft(
    db: Session, user: User, project: Project, text: str, source_type: str = "text"
) -> dict:
    """跑完整上报流水线并落库，返回 need_clarify 分支或工单结果（不提交事务之外的业务判断）。"""
    result = process_report(db, text, source_type, project_id=project.id)
    report = Report(
        project_id=project.id,
        reporter_id=user.id,
        input_type=source_type,
        raw_text=text,
        processed=not result["need_clarify"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if result["need_clarify"]:
        logger.info("隐患上报需澄清 report_id=%s question=%s", report.id, result["question"])
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
    logger.info(
        "AI 生成工单 order=%s risk=%s engine=%s regs=%d",
        order.order_no, order.risk_level, draft["extraction_engine"], len(draft["regulation_refs"]),
    )
    return {
        "need_clarify": False,
        "order": order_to_dict(order),
        "extracted": result["extracted"],
        "regs": result["regs"],
        "alternates": draft["alternates"],
        "match_reason": draft["match_reason"],
    }
