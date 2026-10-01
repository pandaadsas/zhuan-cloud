"""对话 Agent：qwen tool-calling 循环 + SSE 事件生成器。

把进度/统计/规范/周报包装成工具交给 LLM 自主调度，支持多轮追问；
mock 模式不进入本模块，由路由层降级走规则链路（零 API 消耗）。
"""
import json
import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from ..config_runtime import get_cfg
from ..models import Project, User
from ..rag.retriever import search as kb_search
from ..services.weekly import generate_weekly, week_range
from .chat_tools import find_order_markdown, stats_markdown
from .llm import client

logger = logging.getLogger("zhuan.agent")

MAX_ROUNDS = 5  # 工具调用轮数上限，防止死循环
WEEKLY_ROLES = ("safety_officer", "safety_supervisor", "project_manager")

ROLE_LABELS = {
    "safety_officer": "安全员",
    "safety_supervisor": "安全总监",
    "project_manager": "项目经理",
    "responsible": "分包负责人",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_order_progress",
            "description": "查询隐患整改工单的当前状态、责任人与最近流转记录。用户问进度/状态/到哪一步/整改完了吗时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_no": {"type": "string", "description": "工单编号，如 ZA-20260926-001；用户提到编号时传入"},
                    "building": {"type": "string", "description": "楼号，如 3号楼；未提到则不传"},
                    "floor": {"type": "string", "description": "楼层，如 12层 或 B1层；未提到则不传"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_stats",
            "description": "查询当前项目的隐患治理统计：累计/闭环/整改率/超期/风险分布。用户问统计、多少、整改率、超期情况时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_regulations",
            "description": "检索安全规范知识库条款。回答规范要求类问题前必须先调用；一次检索不够时可换关键词多次调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词，如：临边防护栏杆高度要求"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_weekly_report",
            "description": "生成本周项目安全周报（Markdown）。用户要求周报/汇总本周安全情况时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_LABELS = {
    "query_order_progress": "正在查询工单进度…",
    "query_stats": "正在汇总治理统计…",
    "search_regulations": "正在检索规范条款…",
    "generate_weekly_report": "正在生成安全周报…",
}


def _system_prompt(user: User, project: Project) -> str:
    role = ROLE_LABELS.get(user.role, user.role)
    return (
        f"你是筑安云的现场安全AI助手，服务对象是{role}（姓名：{user.name}），当前项目「{project.name}」，"
        "回答使用 Markdown 中文。\n"
        "规则：\n"
        "1. 涉及工单、统计数字、规范条款的问题，必须先调用工具获取真实数据，禁止编造工单号、数字和条款。\n"
        "2. 用户消息省略了上文主语时（如追问「那2号楼呢」），结合对话历史理解后再选工具和参数。\n"
        "3. 规范依据一律来自 search_regulations 返回的条款，引用时标注《规范名》条款号；检索不到就明确说明。\n"
        "4. 调用 generate_weekly_report 后，把返回的周报内容原样输出，不要改写或增删。\n"
        "5. 不需要工具的闲聊/引导类问题直接回答，并适当提示你能帮做什么（查进度、看统计、查规范、生成周报）。"
    )


def _history_messages(history: list[dict]) -> list[dict]:
    return [
        {"role": h["role"], "content": h["content"]}
        for h in history
        if h.get("role") in ("user", "assistant") and h.get("content")
    ]


def _exec_search(db: Session, query: str) -> tuple[str, list[dict]]:
    regs = kb_search(db, query, k=3)
    logger.info("Agent 检索规范 query=%s 命中=%d", query, len(regs))
    refs = [
        {"doc_name": r["doc_name"], "clause_no": r["clause_no"], "title": r["title"]}
        for r in regs
    ]
    return json.dumps(regs, ensure_ascii=False), refs


def _dedupe_refs(refs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in refs:
        key = (r["doc_name"], r["clause_no"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _chunk(text: str, size: int = 60) -> Iterator[str]:
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _stream_llm_round(cfg, messages: list[dict]) -> tuple[list[str], dict[int, dict], str | None]:
    """跑一轮流式补全，返回 (增量文本片段列表, 工具调用槽, 错误信息)。

    网络中断等异常以错误字符串返回，由调用方决定降级或中止。
    """
    content_parts: list[str] = []
    tool_slots: dict[int, dict] = {}
    try:
        stream = client(cfg).chat.completions.create(
            model=cfg.qwen_text_model,
            messages=messages,
            tools=TOOLS,
            stream=True,
            temperature=0.4,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
            for tc in delta.tool_calls or []:
                slot = tool_slots.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        return content_parts, tool_slots, None
    except Exception as e:
        return content_parts, tool_slots, str(e)


def run_agent(
    db: Session,
    user: User,
    project: Project,
    message: str,
    history: list[dict],
) -> Iterator[dict]:
    """执行 agent 循环，逐个 yield SSE 事件 dict。

    LLM 首轮调用就失败时抛出异常，由路由层降级到规则链路；
    已经输出过增量后再失败，直接发 error 事件结束。
    """
    cfg = get_cfg()
    messages = [
        {"role": "system", "content": _system_prompt(user, project)},
        *_history_messages(history),
        {"role": "user", "content": message},
    ]
    refs: list[dict] = []
    weekly_id = None
    streamed_any = False

    for _round in range(MAX_ROUNDS):
        content_parts, tool_slots, err = _stream_llm_round(cfg, messages)
        if err:
            logger.warning("Agent LLM 调用失败：%s", err)
            if streamed_any:
                yield {"type": "error", "message": "AI 服务中断，请重试"}
                return
            raise RuntimeError(err)  # 尚未输出内容，让路由层走规则降级

        for part in content_parts:
            streamed_any = True
            yield {"type": "delta", "text": part}

        if not tool_slots:
            break  # 本轮即最终回答，已流式输出完毕

        assistant_tool_calls = [
            {
                "id": s["id"] or f"call_{i}",
                "type": "function",
                "function": {"name": s["name"], "arguments": s["arguments"] or "{}"},
            }
            for i, s in sorted(tool_slots.items())
        ]
        messages.append({"role": "assistant", "content": "".join(content_parts) or None, "tool_calls": assistant_tool_calls})

        for i, call in enumerate(assistant_tool_calls):
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            logger.info("Agent 工具调用 %s args=%s", name, args)
            yield {"type": "tool", "name": name, "label": TOOL_LABELS.get(name, name), "args": args}

            if name == "generate_weekly_report":
                if user.role not in WEEKLY_ROLES:
                    result = {"error": "周报生成权限为安全员/安全总监/项目经理，请向用户说明，并建议改问进度或统计。"}
                else:
                    report = generate_weekly(db, *week_range(0), user, project_id=project.id)
                    weekly_id = report.id
                    # 周报内容直接原样输出，不走 LLM 改写
                    yield {"type": "refs", "refs": []}
                    for piece in _chunk(report.content_md):
                        streamed_any = True
                        yield {"type": "delta", "text": piece}
                    yield {"type": "done", "weekly_id": weekly_id}
                    return
            elif name == "query_order_progress":
                result = find_order_markdown(
                    db,
                    project.id,
                    order_no=str(args.get("order_no") or ""),
                    building=str(args.get("building") or ""),
                    floor=str(args.get("floor") or ""),
                )
            elif name == "query_stats":
                result = stats_markdown(db, project.id)
            elif name == "search_regulations":
                result, round_refs = _exec_search(db, str(args.get("query", "")))
                refs += round_refs
            else:
                result = {"error": f"未知工具 {name}"}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                }
            )
    else:
        logger.warning("Agent 达到最大工具轮数 %d，强制收尾", MAX_ROUNDS)

    yield {"type": "refs", "refs": _dedupe_refs(refs)}
    yield {"type": "done", "weekly_id": weekly_id}
