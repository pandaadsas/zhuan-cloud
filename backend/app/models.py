from datetime import datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Project(Base):
    """工程项目。

    字段说明:
        name: 项目名称
        location: 项目所在地
        total_area: 总建筑面积
        scale_desc: 规模描述
        current_stage: 当前施工阶段
        note: 备注说明
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    location: Mapped[str] = mapped_column(String(120), default="")
    total_area: Mapped[str] = mapped_column(String(50), default="")
    scale_desc: Mapped[str] = mapped_column(String(255), default="")
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    note: Mapped[str] = mapped_column(Text, default="")


class Subcontractor(Base):
    """分包单位。

    字段说明:
        project_id: 所属项目，可空（兼容历史数据）
        name: 单位名称
        scope: 承包范围
        leader_name: 负责人姓名
        leader_phone: 负责人电话
    """

    __tablename__ = "subcontractors"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    scope: Mapped[str] = mapped_column(String(200), default="")
    leader_name: Mapped[str] = mapped_column(String(50), default="")
    leader_phone: Mapped[str] = mapped_column(String(20), default="")


class User(Base):
    """系统用户。

    字段说明:
        username: 登录用户名（唯一）
        password_hash: 密码哈希
        name: 姓名
        role: 角色（如管理/安全员/分包负责人等）
        phone: 手机号
        email: 邮箱
        subcontractor_id: 所属分包单位，可空
        subcontractor: 所属分包单位关系
    """

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
    """验证码（短信/邮箱），用于登录或找回密码等场景。

    字段说明:
        target: 接收目标（手机号或邮箱）
        channel: 发送渠道（sms/email）
        code: 验证码内容
        used: 是否已使用
        expires_at: 过期时间
        created_at: 创建时间
    """

    __tablename__ = "verify_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(150), index=True)
    channel: Mapped[str] = mapped_column(String(10))
    code: Mapped[str] = mapped_column(String(10))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Zone(Base):
    """施工区域/楼栋。

    字段说明:
        project_id: 所属项目，可空（兼容历史数据）
        name: 区域名称
        zone_type: 区域类型
        floor_count: 楼层数
        current_stage: 当前施工阶段
        subcontractor_id: 负责施工的分包单位，可空
        responsible_user_id: 责任人用户，可空
        project: 所属项目关系
    """

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(60), index=True)
    zone_type: Mapped[str] = mapped_column(String(40), default="")
    floor_count: Mapped[int] = mapped_column(default=0)
    current_stage: Mapped[str] = mapped_column(String(50), default="")
    subcontractor_id: Mapped[int | None] = mapped_column(ForeignKey("subcontractors.id"), nullable=True)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    project: Mapped["Project | None"] = relationship()
    subcontractor: Mapped["Subcontractor | None"] = relationship()
    responsible_user: Mapped["User | None"] = relationship(foreign_keys=[responsible_user_id])


class Report(Base):
    """隐患上报原始记录。

    字段说明:
        project_id: 所属项目，可空（兼容历史数据）
        reporter_id: 上报人用户，可空（匿名上报）
        input_type: 输入类型（text/voice/image）
        raw_text: 原始文本内容
        transcript: 语音转写文本
        image_path: 上传图片路径
        processed: 是否已被 AI 处理并生成工单
        created_at: 上报时间
    """

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    reporter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    input_type: Mapped[str] = mapped_column(String(10), default="text")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    transcript: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str] = mapped_column(String(255), default="")
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class WorkOrder(Base):
    """安全隐患整改工单（核心业务实体）。

    字段说明:
        order_no: 工单编号（唯一）
        project_id: 所属项目，可空（兼容历史数据）
        report_id: 来源上报记录，可空
        title: 工单标题
        building: 楼栋
        floor: 楼层
        spot: 具体部位
        zone_id: 所属区域，可空
        hazard_type: 隐患类型
        description: 隐患描述
        risk_level: 风险等级（高/中/低，默认"中"）
        suggestion: 整改建议
        regulation_refs: 关联法规条款（JSON 数组）
        source_type: 来源类型（text/voice/image）
        responsible_user_id: 整改责任人，可空
        reviewer_id: 审核人，可空
        deadline: 整改期限，可空
        status: 工单状态（如 pending_review/dispatched/closed 等）
        overdue: 是否超期
        rect_note: 整改说明
        rect_images: 整改图片路径列表（JSON 数组）
        dispatched_at: 派单时间
        closed_at: 关单时间
        created_at: 创建时间
        updated_at: 更新时间（自动维护）

    关联关系:
        project: 所属项目
        responsible_user / reviewer: 责任人与审核人用户
        zone: 所属区域
        events: 工单流转事件列表（OrderEvent）
    """

    __tablename__ = "work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    order_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    building: Mapped[str] = mapped_column(String(40), default="")
    floor: Mapped[str] = mapped_column(String(20), default="")
    spot: Mapped[str] = mapped_column(String(80), default="")
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    hazard_type: Mapped[str] = mapped_column(String(60), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(10), default="中")
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
    project: Mapped["Project | None"] = relationship()
    zone: Mapped["Zone | None"] = relationship()
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order")


class OrderEvent(Base):
    """工单流转事件日志，记录工单的每次操作。

    字段说明:
        order_id: 所属工单
        actor: 操作人姓名
        action: 操作动作（如派单/整改/审核等）
        detail: 操作详情
        created_at: 操作时间
        order: 所属工单关系
    """

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("work_orders.id"), index=True)
    actor: Mapped[str] = mapped_column(String(50), default="")
    action: Mapped[str] = mapped_column(String(30), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    order: Mapped["WorkOrder"] = relationship(back_populates="events")


class Regulation(Base):
    """法规条款，用于 RAG 检索为隐患定性提供依据。

    字段说明:
        doc_name: 法规文档名称
        clause_no: 条款编号
        title: 条款标题
        content: 条款内容
        tags: 标签列表（JSON 数组）
        embedding: 向量化表示（JSON 数组，用于相似度检索）
        source: 条款来源：builtin=内置规范（启动时同步）；import=文档导入；空=旧版种子（已退役，启动时清理）
    """

    __tablename__ = "regulations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_name: Mapped[str] = mapped_column(String(80))
    clause_no: Mapped[str] = mapped_column(String(30), default="")
    title: Mapped[str] = mapped_column(String(120), default="")
    content: Mapped[str] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(String(20), default="import")


class WeeklyReport(Base):
    """安全周报。

    字段说明:
        project_id: 所属项目，可空（兼容历史数据）
        week_start: 周起始日期
        week_end: 周结束日期
        content_md: 周报正文（Markdown 格式）
        stats_json: 本周统计数据（JSON 对象）
        created_at: 生成时间
    """

    __tablename__ = "weekly_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    week_start: Mapped[datetime] = mapped_column(Date)
    week_end: Mapped[datetime] = mapped_column(Date)
    content_md: Mapped[str] = mapped_column(Text)
    stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class AppConfig(Base):
    """应用全局配置，单行记录以 JSON 形式存储所有运行时配置。

    字段说明:
        data: 配置内容（JSON 对象）
        updated_at: 最近更新时间（自动维护）
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


class ChatSession(Base):
    """AI 对话会话元数据（≈ Codex rollout 文件的 session_meta 头）。

    字段说明:
        user_id: 归属用户，会话按账号隔离
        project_id: 归属项目，上下文中的工单/统计数据都是项目级
        assistant: 所属智能助手（safety=AI 安全助手 / pm=项目管理助手），会话按助手隔离
        title: 会话标题（首条用户消息截前 20 字）
    """

    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    assistant: Mapped[str] = mapped_column(String(20), default="safety", index=True)
    title: Mapped[str] = mapped_column(String(60), default="新的对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ChatMessage(Base):
    """对话事件行，append-only：只插入不更新，重新生成分支由 parent_message_id 表达。

    字段说明:
        session_id: 所属会话
        parent_message_id: 重新生成时指向被替代的 assistant 行（一期 UI 不启用，字段预留）
        role: user / assistant
        content: 消息正文（原始 Markdown）
        refs: 回答依据的规范条款列表（assistant）
        tool_trace: Agent 工具调用轨迹 [{name, args, at}]（assistant）
        weekly_id: 关联的安全周报 id
    """

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    parent_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(12))
    content: Mapped[str] = mapped_column(Text, default="")
    refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_trace: Mapped[list | None] = mapped_column(JSON, nullable=True)
    weekly_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
