from datetime import datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120), default="")
    total_area: Mapped[str] = mapped_column(String(50), default="")
    scale_desc: Mapped[str] = mapped_column(String(255), default="")
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class Subcontractor(Base):
    __tablename__ = "subcontractors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(String(200), default="")
    leader_name: Mapped[str] = mapped_column(String(50), default="")
    leader_phone: Mapped[str] = mapped_column(String(20), default="")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(30), index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(120), default="", index=True)
    subcontractor_id: Mapped[int | None] = mapped_column(ForeignKey("subcontractors.id"), nullable=True)

    subcontractor: Mapped["Subcontractor | None"] = relationship()


class VerifyCode(Base):
    __tablename__ = "verify_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(150), index=True)  # 邮箱地址或手机号
    channel: Mapped[str] = mapped_column(String(10))  # email / sms
    code: Mapped[str] = mapped_column(String(10))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    zone_type: Mapped[str] = mapped_column(String(40), default="")
    floor_count: Mapped[int] = mapped_column(default=0)
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    subcontractor_id: Mapped[int | None] = mapped_column(ForeignKey("subcontractors.id"), nullable=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    subcontractor: Mapped["Subcontractor | None"] = relationship()
    responsible_user: Mapped["User | None"] = relationship(foreign_keys=[responsible_user_id])


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    input_type: Mapped[str] = mapped_column(String(10), default="text")  # text/voice/image
    raw_text: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(String(255), default="")
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    building: Mapped[str] = mapped_column(String(40), default="")
    floor: Mapped[str] = mapped_column(String(20), default="")
    spot: Mapped[str] = mapped_column(String(80), default="")
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    hazard_type: Mapped[str] = mapped_column(String(60), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(10), default="中")  # 低/中/高/重大
    suggestion: Mapped[str] = mapped_column(Text, default="")
    regulation_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str] = mapped_column(String(10), default="text")
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    overdue: Mapped[bool] = mapped_column(Boolean, default=False)
    rect_note: Mapped[str] = mapped_column(Text, default="")
    rect_images: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    responsible_user: Mapped["User | None"] = relationship(foreign_keys=[responsible_user_id])
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])
    zone: Mapped["Zone | None"] = relationship()
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order")


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    actor: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(30), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped["WorkOrder"] = relationship(back_populates="events")


class Regulation(Base):
    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_name: Mapped[str] = mapped_column(String(80))
    clause_no: Mapped[str] = mapped_column(String(30), default="")
    title: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)


class WeeklyReport(Base):
    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    week_start: Mapped[datetime] = mapped_column(Date)
    week_end: Mapped[datetime] = mapped_column(Date)
    content_md: Mapped[str] = mapped_column(Text)
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
