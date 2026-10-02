"""AI对话助手：LLM Agent（tool-calling + 多轮 + SSE 流式）为主，规则引擎降级。

会话持久化（transcript-as-log）：每个会话是 chat_sessions + chat_messages 中的
一条 append-only 事件日志；恢复会话 = 按 session_id 重放消息行。
"""
import json
import logging
import re
from copy import deepcopy
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..agents.chat_agent import ASSISTANTS, PM_MUTATION_TOOLS, PM_TOOLS, run_agent
from ..agents.chat_tools import classify, fallback_conversation, kb_response, progress_from_msg, stats_markdown, stats_overview
from ..agents.llm import llm_ready
from ..auth import get_current_user
from ..database import SessionLocal, get_db
from ..deps import current_project
from ..models import ChatMessage, ChatPendingAction, ChatSession, Project, User, WorkOrder
from ..schemas import ChatActionIn, ChatIn
from ..serializers import ROLE_LABELS, order_to_dict
from ..services.weekly import generate_weekly, week_range

logger = logging.getLogger("zhuan.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])

HISTORY_TURNS = 10  # 注入 agent 的最大历史条数
HISTORY_TURN_CHARS = 500  # 单条历史截断长度，防止上下文膨胀
LIST_LIMIT = 50  # 会话列表 / 消息恢复的条数上限
TITLE_CHARS = 20  # 会话标题截取长度
_ORDER_NO_RE = re.compile(r"ZA-\d{8}-\d{3}")
_BUILDING_RE = re.compile(r"(\d{1,2})\s*[#号楼栋]")
_FLOOR_RE = re.compile(r"(B\d{1,2}|负?\d{1,2})\s*层")


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


def _rule_fallback(db, user: User, project: Project, msg: str, history=None):
    """规则降级链路：mock 模式 / 未配 key / Agent 首轮失败时启用，协议事件与 Agent 一致。"""
    if not msg:
        yield {"type": "delta", "text": "请输入您的问题，例如：3号楼12层的隐患整改到哪一步了？"}
        yield {"type": "refs", "refs": []}
        yield {"type": "done", "weekly_id": None}
        return

    conversation = fallback_conversation(msg)
    intent = "conversation" if conversation else classify(msg)
    logger.info("AI对话(规则降级) user=%s(%s) intent=%s project=%s msg=%s", user.name, user.role, intent, project.name, msg[:50])
    refs: list[dict] = []
    weekly_id = None

    if intent == "weekly":
        if user.role not in ("safety_officer", "safety_supervisor", "project_manager"):
            reply = "周报生成权限为安全员/安全总监/项目经理。如需了解整改情况，可以直接问我进度或统计。"
        else:
            start, end = week_range(0)
            report = generate_weekly(db, start, end, user, project_id=project.id)
            reply = report.content_md
            weekly_id = report.id
            yield {"type": "artifact", "artifact": {"type": "weekly_report", "title": "安全周报", "data": {"weekly_id": weekly_id}}}
    elif intent == "progress":
        reply = progress_from_msg(db, msg, project_id=project.id)
        query = db.query(WorkOrder).filter(WorkOrder.project_id == project.id)
        if match := _ORDER_NO_RE.search(msg):
            query = query.filter(WorkOrder.order_no == match.group(0))
        if match := _BUILDING_RE.search(msg):
            query = query.filter(WorkOrder.building.like(f"%{match.group(1)}%"))
        if match := _FLOOR_RE.search(msg):
            query = query.filter(WorkOrder.floor.like(f"%{match.group(0).replace(' ', '')}%"))
        order = query.order_by(WorkOrder.created_at.desc()).first()
        orders = []
        if order:
            item = order_to_dict(order, brief=True)
            item["location"] = " · ".join(filter(None, (order.building, order.floor, order.spot)))
            orders.append(item)
        yield {"type": "artifact", "artifact": {"type": "work_order_list", "title": "工单进度", "data": {"orders": orders}}}
    elif intent == "stats":
        reply = stats_markdown(db, project_id=project.id)
        yield {"type": "artifact", "artifact": {"type": "stats_summary", "title": "治理统计", "data": stats_overview(db, project)}}
    elif intent == "kb":
        reply, refs, artifact = kb_response(db, msg, history=history)
        yield {"type": "artifact", "artifact": artifact}

    else:
        reply = conversation or "AI 理解服务暂时不可用，请补充具体对象和需求，例如工单编号、要查询的统计或具体安全问题。"

    yield {"type": "delta", "text": reply}
    yield {"type": "refs", "refs": refs}
    yield {"type": "done", "weekly_id": weekly_id}


def _pm_fallback(msg: str):
    """项目管理助手的降级链路：无规则引擎可复用（安全类意图不适用），给出明确提示。"""
    if not msg:
        yield {"type": "delta", "text": "请输入您的指令，例如：新增一个项目，名称为滨江苑二期。"}
    else:
        yield {"type": "delta", "text": "AI 引擎暂时不可用，项目管理助手暂无法执行操作。请稍后重试，或先到「项目管理」页面手动操作。"}
    yield {"type": "refs", "refs": []}
    yield {"type": "done", "weekly_id": None}


def _load_history(db: Session, session_id: int) -> list[dict]:
    """从库里取最近几轮消息注入 agent（换设备续聊上下文不丢）。"""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id, ChatMessage.content != "")
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_TURNS)
        .all()
    )
    rows.reverse()
    return [{"role": r.role, "content": r.content[:HISTORY_TURN_CHARS]} for r in rows]


def _own_session(db: Session, user: User, project: Project, session_id: int) -> ChatSession:
    """按 id 取会话，强制归属校验：非本人/非当前项目一律 404，防越权读取。"""
    s = (
        db.query(ChatSession)
        .filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
            ChatSession.project_id == project.id,
        )
        .first()
    )
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return s


@router.post("")
def chat(
    payload: ChatIn,
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    """SSE 流式对话。事件：tool（工具调用）/ delta（回答增量）/ refs（条款引用）/ done（结束，携带 session_id）。"""

    profile = ASSISTANTS.get(payload.assistant)
    if profile is None:
        raise HTTPException(status_code=400, detail="未知的助手类型")
    if profile.roles and user.role not in profile.roles:
        allowed = "、".join(ROLE_LABELS.get(r, r) for r in profile.roles)
        raise HTTPException(status_code=403, detail=f"「{profile.title}」仅对{allowed}开放")

    msg = (payload.message or "").strip()

    def event_stream():
        # 流式响应期间依赖注入的 db 会话已不可靠，这里自建会话；user/project 属性已在鉴权时加载
        db = SessionLocal()
        session: ChatSession | None = None
        acc = {"content": "", "refs": None, "tool_trace": [], "artifacts": [], "weekly_id": None}
        persisted = False

        def persist() -> int | None:
            """把本轮对话一次性落库（会话惰性创建，标题取首条消息）。返回 session_id。"""
            nonlocal persisted, session
            if persisted or not msg:
                return session.id if session else None
            persisted = True
            try:
                if session is None:
                    session = ChatSession(
                        user_id=user.id,
                        project_id=project.id,
                        assistant=profile.key,
                        title=msg[:TITLE_CHARS],
                    )
                    db.add(session)
                    db.flush()
                db.add(ChatMessage(session_id=session.id, role="user", content=msg))
                if acc["content"] or acc["tool_trace"] or acc["artifacts"]:
                    assistant_message = ChatMessage(
                        session_id=session.id,
                        role="assistant",
                        content=acc["content"],
                        refs=acc["refs"],
                        tool_trace=acc["tool_trace"] or None,
                        artifacts=acc["artifacts"] or None,
                        weekly_id=acc["weekly_id"],
                    )
                    db.add(assistant_message)
                    db.flush()
                    tokens = [
                        a.get("data", {}).get("token")
                        for a in acc["artifacts"]
                        if a.get("type") == "change_preview"
                    ]
                    if tokens:
                        db.query(ChatPendingAction).filter(ChatPendingAction.token.in_(tokens)).update(
                            {ChatPendingAction.message_id: assistant_message.id}, synchronize_session=False
                        )
                session.updated_at = datetime.now()
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("对话落库失败 session=%s", session.id if session else None)
            return session.id if session else None

        def handle(ev: dict) -> dict:
            """转发前累积事件内容，供 finally 兜底落库。"""
            t = ev.get("type")
            if t == "delta":
                acc["content"] += ev.get("text", "")
            elif t == "tool":
                acc["tool_trace"].append(
                    {"name": ev.get("name"), "args": ev.get("args"), "at": datetime.now().strftime("%H:%M:%S")}
                )
            elif t == "refs":
                acc["refs"] = ev.get("refs") or None
            elif t == "artifact" and ev.get("artifact"):
                acc["artifacts"].append(ev["artifact"])
            elif t == "done":
                acc["weekly_id"] = ev.get("weekly_id")
            return ev

        def stream(gen):
            for ev in gen:
                ev = handle(ev)
                if ev.get("type") == "done":
                    # done 事件需要在流结束前把 session_id 带回前端，落库提前到此处执行
                    ev = dict(ev, session_id=persist())
                yield _sse(ev)

        try:
            if payload.session_id:
                # 归属校验失败时不报错，静默当作新会话处理（done 会返回新 id）；
                # 会话同时按助手隔离，安全助手的会话不会被项目管理助手复用
                session = (
                    db.query(ChatSession)
                    .filter(
                        ChatSession.id == payload.session_id,
                        ChatSession.user_id == user.id,
                        ChatSession.project_id == project.id,
                        ChatSession.assistant == profile.key,
                    )
                    .first()
                )
            history = _load_history(db, session.id) if session else []
            logger.info(
                "AI对话 user=%s(%s) session=%s project=%s msg=%s",
                user.name, user.role, session.id if session else None, project.name, msg[:50],
            )

            if msg and llm_ready():
                try:
                    yield from stream(
                        run_agent(
                            db,
                            user,
                            project,
                            msg,
                            history,
                            tools=profile.tools,
                            system_prompt=profile.prompt_builder(user, project),
                        )
                    )
                    return
                except Exception:
                    logger.exception("Agent 链路失败，降级规则引擎 user=%s msg=%s", user.name, msg[:50])
            if profile.key == "pm":
                yield from stream(_pm_fallback(msg))
            else:
                yield from stream(_rule_fallback(db, user, project, msg, history=history))
        finally:
            persist()  # 客户端中断 / 异常时兜底落库
            db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions")
def list_sessions(
    limit: int = 20,
    assistant: str = "safety",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    rows = (
        db.query(ChatSession)
        .filter(
            ChatSession.user_id == user.id,
            ChatSession.project_id == project.id,
            ChatSession.assistant == assistant,
        )
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .limit(min(max(limit, 1), LIST_LIMIT))
        .all()
    )
    return [
        {
            "id": s.id,
            "title": s.title,
            "updated_at": s.updated_at.strftime("%m-%d %H:%M") if s.updated_at else "",
        }
        for s in rows
    ]


@router.get("/sessions/{session_id}/messages")
def session_messages(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    s = _own_session(db, user, project, session_id)
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == s.id)
        .order_by(ChatMessage.id.desc())
        .limit(LIST_LIMIT)
        .all()
    )
    rows.reverse()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "refs": m.refs or [],
            "tool_trace": m.tool_trace or [],
            "artifacts": m.artifacts or [],
            "weekly_id": m.weekly_id,
            "created_at": m.created_at.strftime("%m-%d %H:%M") if m.created_at else "",
        }
        for m in rows
    ]


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    s = _own_session(db, user, project, session_id)
    db.query(ChatMessage).filter(ChatMessage.session_id == s.id).delete()
    db.delete(s)
    db.commit()
    return {"ok": True}


def _store_action_result(db: Session, action: ChatPendingAction, status: str, result) -> dict:
    action.status = status
    action.result = result if isinstance(result, dict) else {"message": str(result)}
    action.resolved_at = datetime.now()
    artifact = None
    if action.message_id:
        message = db.get(ChatMessage, action.message_id)
        if message:
            artifacts = deepcopy(message.artifacts or [])
            for item in artifacts:
                data = item.get("data") or {}
                if data.get("token") == action.token:
                    data = dict(data, status=status, result=action.result)
                    item["data"] = data
                    artifact = item
                    break
            message.artifacts = artifacts
    return artifact or {
        "type": "change_preview",
        "title": "业务变更",
        "data": {"token": action.token, "operation": action.operation, "status": status, "result": action.result},
    }


@router.post("/actions/{token}")
def resolve_action(
    token: str,
    payload: ChatActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    """确认或取消项目管理助手的单次写操作。自然语言消息无法绕过此入口。"""
    action = (
        db.query(ChatPendingAction)
        .filter(
            ChatPendingAction.token == token,
            ChatPendingAction.user_id == user.id,
            ChatPendingAction.project_id == project.id,
        )
        .first()
    )
    if action is None:
        raise HTTPException(status_code=404, detail="确认操作不存在或不属于当前账号")
    if action.status != "pending":
        raise HTTPException(status_code=409, detail="该操作已经处理，不能重复提交")
    if action.expires_at < datetime.now():
        artifact = _store_action_result(db, action, "expired", {"message": "确认已过期，请重新发起操作"})
        db.commit()
        raise HTTPException(status_code=410, detail=artifact["data"]["result"]["message"])

    claimed = (
        db.query(ChatPendingAction)
        .filter(ChatPendingAction.id == action.id, ChatPendingAction.status == "pending")
        .update({ChatPendingAction.status: "resolving"}, synchronize_session=False)
    )
    if claimed != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="该操作正在处理或已经完成")
    db.commit()
    db.refresh(action)

    if not payload.confirm:
        artifact = _store_action_result(db, action, "cancelled", {"message": "已取消，本次未修改任何数据"})
        db.commit()
        return {"ok": True, "artifact": artifact}

    tool = next((item for item in PM_TOOLS if item.name == action.operation), None)
    if tool is None or action.operation not in PM_MUTATION_TOOLS:
        raise HTTPException(status_code=400, detail="不支持的确认操作")
    if tool.roles and user.role not in tool.roles:
        raise HTTPException(status_code=403, detail="当前角色无权执行该操作")

    output = tool.executor(db, user, project, dict(action.args or {}))
    result = output[0] if isinstance(output, tuple) else output
    status = "failed" if isinstance(result, dict) and result.get("error") else "completed"
    artifact = _store_action_result(db, action, status, result)
    db.commit()
    return {"ok": status == "completed", "artifact": artifact}


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    """把会话导出为 Codex rollout 同款 JSONL（首行 meta，逐行事件），用于留证审计。"""
    s = _own_session(db, user, project, session_id)
    rows = db.query(ChatMessage).filter(ChatMessage.session_id == s.id).order_by(ChatMessage.id.asc()).all()

    def dump(obj: dict) -> str:
        return json.dumps(obj, ensure_ascii=False)

    lines = [
        dump(
            {
                "timestamp": s.created_at.isoformat() if s.created_at else "",
                "type": "session_meta",
                "payload": {
                    "session_id": s.id,
                    "user_id": s.user_id,
                    "project_id": s.project_id,
                    "title": s.title,
                    "generator": "zhuan-cloud",
                },
            }
        )
    ]
    for m in rows:
        lines.append(
            dump(
                {
                    "timestamp": m.created_at.isoformat() if m.created_at else "",
                    "type": "message",
                    "payload": {
                        "role": m.role,
                        "content": m.content,
                        "refs": m.refs,
                        "tool_trace": m.tool_trace,
                        "weekly_id": m.weekly_id,
                    },
                }
            )
        )
    return Response(
        "\n".join(lines) + "\n",
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="chat-session-{s.id}.jsonl"'},
    )
