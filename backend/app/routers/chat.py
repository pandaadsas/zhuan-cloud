"""AI对话助手：LLM Agent（tool-calling + 多轮 + SSE 流式）为主，规则引擎降级。

会话持久化（transcript-as-log）：每个会话是 chat_sessions + chat_messages 中的
一条 append-only 事件日志；恢复会话 = 按 session_id 重放消息行。
"""
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from ..agents.chat_agent import run_agent
from ..agents.chat_tools import classify, kb_answer, progress_from_msg, stats_markdown
from ..agents.llm import llm_ready
from ..auth import get_current_user
from ..database import SessionLocal, get_db
from ..deps import current_project
from ..models import ChatMessage, ChatSession, Project, User
from ..schemas import ChatIn
from ..services.weekly import generate_weekly, week_range

logger = logging.getLogger("zhuan.chat")
router = APIRouter(prefix="/api/chat", tags=["chat"])

HISTORY_TURNS = 10  # 注入 agent 的最大历史条数
HISTORY_TURN_CHARS = 500  # 单条历史截断长度，防止上下文膨胀
LIST_LIMIT = 50  # 会话列表 / 消息恢复的条数上限
TITLE_CHARS = 20  # 会话标题截取长度


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


def _rule_fallback(db, user: User, project: Project, msg: str):
    """规则降级链路：mock 模式 / 未配 key / Agent 首轮失败时启用，协议事件与 Agent 一致。"""
    if not msg:
        yield {"type": "delta", "text": "请输入您的问题，例如：3号楼12层的隐患整改到哪一步了？"}
        yield {"type": "refs", "refs": []}
        yield {"type": "done", "weekly_id": None}
        return

    intent = classify(msg)
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
    elif intent == "progress":
        reply = progress_from_msg(db, msg, project_id=project.id)
    elif intent == "stats":
        reply = stats_markdown(db, project_id=project.id)
    else:
        reply, refs = kb_answer(db, msg)

    yield {"type": "delta", "text": reply}
    yield {"type": "refs", "refs": refs}
    yield {"type": "done", "weekly_id": weekly_id}


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

    msg = (payload.message or "").strip()

    def event_stream():
        # 流式响应期间依赖注入的 db 会话已不可靠，这里自建会话；user/project 属性已在鉴权时加载
        db = SessionLocal()
        session: ChatSession | None = None
        acc = {"content": "", "refs": None, "tool_trace": [], "weekly_id": None}
        persisted = False

        def persist() -> int | None:
            """把本轮对话一次性落库（会话惰性创建，标题取首条消息）。返回 session_id。"""
            nonlocal persisted, session
            if persisted or not msg:
                return session.id if session else None
            persisted = True
            try:
                if session is None:
                    session = ChatSession(user_id=user.id, project_id=project.id, title=msg[:TITLE_CHARS])
                    db.add(session)
                    db.flush()
                db.add(ChatMessage(session_id=session.id, role="user", content=msg))
                if acc["content"] or acc["tool_trace"]:
                    db.add(
                        ChatMessage(
                            session_id=session.id,
                            role="assistant",
                            content=acc["content"],
                            refs=acc["refs"],
                            tool_trace=acc["tool_trace"] or None,
                            weekly_id=acc["weekly_id"],
                        )
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
                # 归属校验失败时不报错，静默当作新会话处理（done 会返回新 id）
                session = (
                    db.query(ChatSession)
                    .filter(
                        ChatSession.id == payload.session_id,
                        ChatSession.user_id == user.id,
                        ChatSession.project_id == project.id,
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
                    yield from stream(run_agent(db, user, project, msg, history))
                    return
                except Exception:
                    logger.exception("Agent 链路失败，降级规则引擎 user=%s msg=%s", user.name, msg[:50])
            yield from stream(_rule_fallback(db, user, project, msg))
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    project: Project = Depends(current_project),
):
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id, ChatSession.project_id == project.id)
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
