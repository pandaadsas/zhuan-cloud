"""对话 Agent：qwen tool-calling 循环 + SSE 事件生成器。

工具采用注册表模式：schema / 执行体 / 角色权限 / 前端状态文案声明在一处；
工具可返回 Terminal 把内容直接流式下发（长周报场景，不经 LLM 改写）。
mock 模式不进入本模块，由路由层降级走规则链路（零 API 消耗）。
"""
import json
import logging
from collections.abc import Iterator

from sqlalchemy.orm import Session

from ..config_runtime import get_cfg
from ..models import Project, User
from .chat_tools import (
    find_order_markdown,
    orders_list_markdown,
    site_directory,
    stats_overview,
    submit_hazard,
    weekly_get_md,
    weekly_list,
)
from .llm import client
from . import pm_tools

logger = logging.getLogger("zhuan.agent")

MAX_ROUNDS = 5  # 工具调用轮数上限，防止死循环
WEEKLY_ROLES = ("safety_officer", "safety_supervisor", "project_manager")
REPORT_ROLES = ("safety_officer", "safety_supervisor")

ROLE_LABELS = {
    "safety_officer": "安全员",
    "safety_supervisor": "安全总监",
    "project_manager": "项目经理",
    "responsible": "分包负责人",
}


class Terminal:
    """终端工具输出：内容直接流式下发给用户，不经 LLM 改写（长周报等场景）。"""

    def __init__(self, text: str, refs: list | None = None, weekly_id: int | None = None):
        self.text = text
        self.refs = refs or []
        self.weekly_id = weekly_id


class Tool:
    """注册项：schema、执行体、角色白名单（None 不限）、前端状态文案。"""

    def __init__(self, name: str, description: str, parameters: dict, executor, label: str, roles: tuple | None = None):
        self.name = name
        self.executor = executor
        self.label = label
        self.roles = roles
        self.schema = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }


def _exec_query_order(db: Session, user: User, project: Project, args: dict):
    md = find_order_markdown(
        db,
        project.id,
        order_no=str(args.get("order_no") or ""),
        building=str(args.get("building") or ""),
        floor=str(args.get("floor") or ""),
    )
    return md, []


def _exec_list_orders(db: Session, user: User, project: Project, args: dict):
    md = orders_list_markdown(
        db,
        user,
        project.id,
        status=str(args.get("status") or ""),
        risk=str(args.get("risk") or ""),
        keyword=str(args.get("keyword") or ""),
        mine=bool(args.get("mine")),
    )
    return md, []


def _exec_stats(db: Session, user: User, project: Project, args: dict):
    return stats_overview(db, project), []


def _exec_search(db: Session, user: User, project: Project, args: dict):
    from ..rag.retriever import search as kb_search

    query = str(args.get("query", ""))
    regs = kb_search(db, query, k=3)
    logger.info("Agent 检索规范 query=%s 命中=%d", query, len(regs))
    refs = [{"doc_name": r["doc_name"], "clause_no": r["clause_no"], "title": r["title"]} for r in regs]
    return json.dumps(regs, ensure_ascii=False), refs


def _exec_generate_weekly(db: Session, user: User, project: Project, args: dict):
    from ..services.weekly import generate_weekly, week_range

    try:
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    report = generate_weekly(db, *week_range(offset), user, project_id=project.id)
    return Terminal(report.content_md, refs=[], weekly_id=report.id)


def _exec_weekly_list(db: Session, user: User, project: Project, args: dict):
    return weekly_list(db, project.id), []


def _exec_weekly_get(db: Session, user: User, project: Project, args: dict):
    try:
        offset = int(args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    md = weekly_get_md(db, project.id, offset)
    if not md:
        return {"error": "该周还没有周报，可以调用 generate_weekly_report 生成后再查看。"}, []
    return Terminal(md, refs=[])


def _exec_directory(db: Session, user: User, project: Project, args: dict):
    return site_directory(db, project.id, str(args.get("kind") or "")), []


def _exec_submit_hazard(db: Session, user: User, project: Project, args: dict):
    return submit_hazard(db, user, project, str(args.get("text") or ""))


TOOLS = [
    Tool(
        "query_order_progress",
        "查询单个隐患整改工单的当前状态、责任人与最近流转记录。用户问进度/状态/到哪一步/整改完了吗时调用。",
        {
            "type": "object",
            "properties": {
                "order_no": {"type": "string", "description": "工单编号，如 ZA-20260926-001；用户提到编号时传入"},
                "building": {"type": "string", "description": "楼号，如 3号楼；未提到则不传"},
                "floor": {"type": "string", "description": "楼层，如 12层 或 B1层；未提到则不传"},
            },
        },
        _exec_query_order,
        "正在查询工单进度…",
    ),
    Tool(
        "list_orders",
        "按条件筛选工单列表（最多8条）。用户想看一批工单（如：待审核的工单、高风险隐患、超期的有哪些）时调用。",
        {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending_review", "dispatched", "rectifying", "recheck", "closed", "rejected"], "description": "工单状态筛选，不传则不过滤"},
                "risk": {"type": "string", "enum": ["低", "中", "高", "重大"], "description": "风险等级筛选，不传则不过滤"},
                "keyword": {"type": "string", "description": "标题/描述关键词，如：临边、动火"},
                "mine": {"type": "boolean", "description": "是否只看用户本人负责的工单"},
            },
        },
        _exec_list_orders,
        "正在筛选工单…",
    ),
    Tool(
        "query_stats",
        "查询项目隐患治理全量统计：累计/闭环/整改率、状态与风险分布、隐患类型Top6、近8周上报与闭环趋势、超期明细。用户问统计、多少、整改率、趋势、超期情况时调用。",
        {"type": "object", "properties": {}},
        _exec_stats,
        "正在汇总治理统计…",
    ),
    Tool(
        "search_regulations",
        "检索安全规范知识库条款。回答规范要求类问题前必须先调用；一次检索不够时可换关键词多次调用。",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词，如：临边防护栏杆高度要求"},
            },
            "required": ["query"],
        },
        _exec_search,
        "正在检索规范条款…",
    ),
    Tool(
        "generate_weekly_report",
        "生成项目安全周报（Markdown）并保存。offset=-1 表示上周，默认本周。",
        {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "description": "周偏移：0=本周，-1=上周，默认0"},
            },
        },
        _exec_generate_weekly,
        "正在生成安全周报…",
        roles=WEEKLY_ROLES,
    ),
    Tool(
        "list_weekly_reports",
        "查询历史周报列表（最近10篇的周期与摘要）。用户想看有哪些周报时调用。",
        {"type": "object", "properties": {}},
        _exec_weekly_list,
        "正在查询历史周报…",
        roles=WEEKLY_ROLES,
    ),
    Tool(
        "get_weekly_report",
        "取某一篇历史周报的全文。offset=0 本周、-1 上周，以此类推。",
        {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "description": "周偏移：0=本周，-1=上周，默认0"},
            },
        },
        _exec_weekly_get,
        "正在调取周报全文…",
        roles=WEEKLY_ROLES,
    ),
    Tool(
        "query_site_directory",
        "查询项目的责任区域、分包单位、分包负责人目录。回答'3号楼是谁的责任区''有哪些分包''负责人是谁'类问题时调用。",
        {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["zones", "subcontractors", "responsible"], "description": "zones=责任区域，subcontractors=分包单位，responsible=分包负责人"},
            },
            "required": ["kind"],
        },
        _exec_directory,
        "正在查询项目目录…",
    ),
    Tool(
        "submit_hazard_report",
        "代用户提交隐患上报：AI 抽取信息、匹配责任人与规范依据，生成待审核工单。用户明确要求上报/建单时才调用；信息不足时工具会返回追问。",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "用户对隐患的完整描述（位置+问题），把对话中已确认的信息合并成一段话"},
            },
            "required": ["text"],
        },
        _exec_submit_hazard,
        "正在提交隐患上报…",
        roles=REPORT_ROLES,
    ),
]

TOOL_MAP = {t.name: t for t in TOOLS}


# ---------- 项目管理助手工具（仅项目经理可见） ----------


def _exec_pm_list_projects(db: Session, user: User, project: Project, args: dict):
    return pm_tools.projects_markdown(db), []


def _exec_pm_create_project(db: Session, user: User, project: Project, args: dict):
    return pm_tools.create_project(db, user, args)


def _exec_pm_update_project(db: Session, user: User, project: Project, args: dict):
    return pm_tools.update_project(db, user, project, args)


def _exec_pm_list_zones(db: Session, user: User, project: Project, args: dict):
    pid = args.get("project_id")
    if pid and int(pid) != project.id:
        return pm_tools.zones_markdown(db, int(pid), f"项目 #{pid}"), []
    return pm_tools.zones_markdown(db, project.id, project.name), []


def _exec_pm_create_zone(db: Session, user: User, project: Project, args: dict):
    return pm_tools.create_zone(db, user, project, args)


def _exec_pm_update_zone(db: Session, user: User, project: Project, args: dict):
    return pm_tools.update_zone(db, user, project, args)


def _exec_pm_delete_zone(db: Session, user: User, project: Project, args: dict):
    return pm_tools.delete_zone(db, user, project, args)


def _exec_pm_list_subs(db: Session, user: User, project: Project, args: dict):
    pid = args.get("project_id")
    if pid and int(pid) != project.id:
        return pm_tools.subs_markdown(db, int(pid), f"项目 #{pid}"), []
    return pm_tools.subs_markdown(db, project.id, project.name), []


def _exec_pm_create_sub(db: Session, user: User, project: Project, args: dict):
    return pm_tools.create_subcontractor(db, user, project, args)


def _exec_pm_update_sub(db: Session, user: User, project: Project, args: dict):
    return pm_tools.update_subcontractor(db, user, project, args)


def _exec_pm_list_users(db: Session, user: User, project: Project, args: dict):
    return pm_tools.responsible_users_markdown(db, project.id, project.name), []


PM_ROLES = ("project_manager",)

PM_TOOLS = [
    Tool(
        "list_projects",
        "查询平台上全部项目的列表（含编号、地点、规模、阶段、区域与分包数量）。编辑项目或跨项目操作前先调用确认目标编号。",
        {"type": "object", "properties": {}},
        _exec_pm_list_projects,
        "正在查询项目列表…",
        roles=PM_ROLES,
    ),
    Tool(
        "create_project",
        "新增项目。name 必填；信息不全时先向用户追问，不要凭空编造。",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "项目名称（必填）"},
                "location": {"type": "string", "description": "项目地点"},
                "total_area": {"type": "string", "description": "总建筑面积，如 12.6万㎡"},
                "scale_desc": {"type": "string", "description": "规模描述"},
                "current_stage": {"type": "string", "description": "当前阶段，如 基础施工、主体结构"},
                "note": {"type": "string", "description": "备注"},
            },
            "required": ["name"],
        },
        _exec_pm_create_project,
        "正在新增项目…",
        roles=PM_ROLES,
    ),
    Tool(
        "update_project",
        "编辑项目信息。project_id 不传时默认编辑当前项目；只传需要修改的字段，未传字段保持不变。",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "目标项目编号，不传则编辑当前项目"},
                "name": {"type": "string", "description": "项目名称"},
                "location": {"type": "string", "description": "项目地点"},
                "total_area": {"type": "string", "description": "总建筑面积"},
                "scale_desc": {"type": "string", "description": "规模描述"},
                "current_stage": {"type": "string", "description": "当前阶段"},
                "note": {"type": "string", "description": "备注"},
            },
        },
        _exec_pm_update_project,
        "正在编辑项目信息…",
        roles=PM_ROLES,
    ),
    Tool(
        "list_zones",
        "查询项目的责任区域列表（含编号、类型、层数、阶段、分包、责任人）。编辑区域前先调用确认编号。",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "目标项目编号，不传则查当前项目"},
            },
        },
        _exec_pm_list_zones,
        "正在查询责任区域…",
        roles=PM_ROLES,
    ),
    Tool(
        "create_zone",
        "在项目中新增责任区域。name 必填；分包和责任人可传编号或名称，信息不全时先向用户确认。",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "区域名称（必填），如 3号楼"},
                "project_id": {"type": "integer", "description": "目标项目编号，不传则建在当前项目"},
                "zone_type": {"type": "string", "description": "区域类型，如 住宅楼、地下室"},
                "floor_count": {"type": "integer", "description": "层数"},
                "current_stage": {"type": "string", "description": "当前阶段，如 主体结构"},
                "subcontractor_id": {"type": "integer", "description": "所属分包编号（与 subcontractor_name 二选一）"},
                "subcontractor_name": {"type": "string", "description": "所属分包名称（与 subcontractor_id 二选一）"},
                "responsible_user_id": {"type": "integer", "description": "责任人用户编号（与 responsible_user_name 二选一）"},
                "responsible_user_name": {"type": "string", "description": "责任人姓名（与 responsible_user_id 二选一）"},
            },
            "required": ["name"],
        },
        _exec_pm_create_zone,
        "正在新增责任区域…",
        roles=PM_ROLES,
    ),
    Tool(
        "update_zone",
        "编辑责任区域信息（名称/类型/层数/阶段/分包/责任人）。zone_id 必填，只传需要修改的字段。",
        {
            "type": "object",
            "properties": {
                "zone_id": {"type": "integer", "description": "区域编号（必填），从 list_zones 结果获取"},
                "name": {"type": "string", "description": "区域名称"},
                "zone_type": {"type": "string", "description": "区域类型"},
                "floor_count": {"type": "integer", "description": "层数"},
                "current_stage": {"type": "string", "description": "当前阶段"},
                "subcontractor_id": {"type": "integer", "description": "所属分包编号（与 subcontractor_name 二选一）"},
                "subcontractor_name": {"type": "string", "description": "所属分包名称（与 subcontractor_id 二选一）"},
                "responsible_user_id": {"type": "integer", "description": "责任人用户编号（与 responsible_user_name 二选一）"},
                "responsible_user_name": {"type": "string", "description": "责任人姓名（与 responsible_user_id 二选一）"},
            },
            "required": ["zone_id"],
        },
        _exec_pm_update_zone,
        "正在编辑责任区域…",
        roles=PM_ROLES,
    ),
    Tool(
        "delete_zone",
        "删除责任区域。仅在用户明确确认删除后调用；区域有关联工单时无法删除。调用前先说明将删除哪个区域。",
        {
            "type": "object",
            "properties": {
                "zone_id": {"type": "integer", "description": "区域编号（必填），从 list_zones 结果获取"},
            },
            "required": ["zone_id"],
        },
        _exec_pm_delete_zone,
        "正在删除责任区域…",
        roles=PM_ROLES,
    ),
    Tool(
        "list_subcontractors",
        "查询项目的分包单位列表（含编号、承包范围、负责人及电话）。编辑分包前先调用确认编号。",
        {
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "目标项目编号，不传则查当前项目"},
            },
        },
        _exec_pm_list_subs,
        "正在查询分包单位…",
        roles=PM_ROLES,
    ),
    Tool(
        "create_subcontractor",
        "在项目中新增分包单位。name 必填；信息不全时先向用户确认。",
        {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "分包单位名称（必填）"},
                "project_id": {"type": "integer", "description": "目标项目编号，不传则建在当前项目"},
                "scope": {"type": "string", "description": "承包范围，如 主体结构、机电安装"},
                "leader_name": {"type": "string", "description": "分包负责人姓名"},
                "leader_phone": {"type": "string", "description": "分包负责人电话"},
            },
            "required": ["name"],
        },
        _exec_pm_create_sub,
        "正在新增分包单位…",
        roles=PM_ROLES,
    ),
    Tool(
        "update_subcontractor",
        "编辑分包单位信息。subcontractor_id 必填，只传需要修改的字段。",
        {
            "type": "object",
            "properties": {
                "subcontractor_id": {"type": "integer", "description": "分包单位编号（必填），从 list_subcontractors 结果获取"},
                "name": {"type": "string", "description": "分包单位名称"},
                "scope": {"type": "string", "description": "承包范围"},
                "leader_name": {"type": "string", "description": "分包负责人姓名"},
                "leader_phone": {"type": "string", "description": "分包负责人电话"},
            },
            "required": ["subcontractor_id"],
        },
        _exec_pm_update_sub,
        "正在编辑分包单位…",
        roles=PM_ROLES,
    ),
    Tool(
        "list_responsible_users",
        "查询当前项目可指派的分包负责人名单（含编号、账号、所属分包）。为责任区域指定责任人时先调用确认人选。",
        {"type": "object", "properties": {}},
        _exec_pm_list_users,
        "正在查询负责人名单…",
        roles=PM_ROLES,
    ),
]


class AssistantProfile:
    """一个智能助手 = 工具集 + 系统提示词 + 可见角色；对话与会话按 key 隔离。"""

    def __init__(self, key: str, title: str, roles: tuple | None, tools: list[Tool], prompt_builder):
        self.key = key
        self.title = title
        self.roles = roles
        self.tools = tools
        self.prompt_builder = prompt_builder


def _pm_system_prompt(user: User, project: Project) -> str:
    return (
        f"你是筑安云的项目管理助手，服务对象是项目经理（姓名：{user.name}），当前项目「{project.name}」，"
        "回答使用 Markdown 中文。\n"
        "你的职责是通过对话完成项目管理工作：新增/编辑项目、管理责任区域（含指派分包与责任人）、管理分包单位。\n"
        "规则：\n"
        "1. 查询类问题（项目列表、区域列表、分包列表、负责人名单）必须先调用工具获取真实数据，禁止编造编号和名称。\n"
        "2. 新增/编辑前把用户口述整理成字段；必填项缺失（项目名称/区域名称/分包名称）时先追问，不要编造。\n"
        "3. 编辑/删除前必须先调用对应 list 工具确认目标编号，并向用户复述将要执行的修改，得到确认后再调用写工具。\n"
        "4. 删除责任区域属高危操作：调用 delete_zone 前必须获得用户对具体区域的明确确认；有关联工单时工具会拒绝删除，此时建议改用编辑。\n"
        "5. 操作成功后用一两句话汇报结果（保留编号等关键信息），必要时提示可继续完善其他字段。\n"
        "6. 工具返回 error 时，向用户说明原因并给出建议（如名称重复、编号不存在、缺少权限）。\n"
        "7. 与项目管理无关的问题（隐患上报、工单进度、周报等），告知用户请前往「AI 安全助手」咨询。"
    )


def _system_prompt(user: User, project: Project) -> str:
    role = ROLE_LABELS.get(user.role, user.role)
    return (
        f"你是筑安云的现场安全AI助手，服务对象是{role}（姓名：{user.name}），当前项目「{project.name}」，"
        "回答使用 Markdown 中文。\n"
        "规则：\n"
        "1. 涉及工单、统计数字、规范条款、区域/分包/周报的问题，必须先调用工具获取真实数据，禁止编造工单号、数字和条款。\n"
        "2. 用户消息省略了上文主语时（如追问「那2号楼呢」），结合对话历史理解后再选工具和参数。\n"
        "3. 规范依据一律来自 search_regulations 返回的条款，引用时标注《规范名》条款号；检索不到就明确说明。\n"
        "4. 调用 generate_weekly_report / get_weekly_report 后，把返回内容原样输出，不要改写或增删。\n"
        "5. 用户想报隐患时调用 submit_hazard_report：若结果带 need_clarify=true，把其中的 question 原样问用户，"
        "拿到补充信息后把对话中已确认的内容合并成一段完整描述再次调用；成功后提醒用户工单已生成、"
        "待安全员在「整改工单」页审核派单。\n"
        "6. 工具返回 error 时，向用户委婉说明原因并给出替代建议。\n"
        "7. 与平台业务无关的问题可简要回答，随后引导回你的能力：查工单进度、筛选工单、治理统计、查规范、"
        "查/生成周报、上报隐患、查区域与分包目录。"
    )


ASSISTANTS = {
    "safety": AssistantProfile("safety", "AI 安全助手", None, TOOLS, _system_prompt),
    "pm": AssistantProfile("pm", "项目管理助手", PM_ROLES, PM_TOOLS, _pm_system_prompt),
}

def _history_messages(history: list[dict]) -> list[dict]:
    return [
        {"role": h["role"], "content": h["content"]}
        for h in history
        if h.get("role") in ("user", "assistant") and h.get("content")
    ]


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


def _stream_llm_round(cfg, messages: list[dict], tool_schemas: list[dict]) -> tuple[list[str], dict[int, dict], str | None]:
    """跑一轮流式补全，返回 (增量文本片段列表, 工具调用槽, 错误信息)。

    网络中断等异常以错误字符串返回，由调用方决定降级或中止。
    """
    content_parts: list[str] = []
    tool_slots: dict[int, dict] = {}
    try:
        stream = client(cfg).chat.completions.create(
            model=cfg.qwen_text_model,
            messages=messages,
            tools=tool_schemas,
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
    tools: list[Tool] | None = None,
    system_prompt: str | None = None,
) -> Iterator[dict]:
    """执行 agent 循环，逐个 yield SSE 事件 dict。

    tools / system_prompt 决定助手画像（默认 = 安全助手）；
    LLM 首轮调用就失败时抛出异常，由路由层降级到规则链路；
    已经输出过增量后再失败，直接发 error 事件结束。
    """
    cfg = get_cfg()
    tool_list = tools if tools is not None else TOOLS
    tool_map = {t.name: t for t in tool_list}
    messages = [
        {"role": "system", "content": system_prompt or _system_prompt(user, project)},
        *_history_messages(history),
        {"role": "user", "content": message},
    ]
    refs: list[dict] = []
    weekly_id = None
    streamed_any = False

    for _round in range(MAX_ROUNDS):
        content_parts, tool_slots, err = _stream_llm_round(cfg, messages, [t.schema for t in tool_list])
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
            yield {"type": "tool", "name": name, "label": tool_map[name].label if name in tool_map else name, "args": args}

            tool = tool_map.get(name)
            if tool is None:
                result, round_refs = {"error": f"未知工具 {name}"}, []
            elif tool.roles and user.role not in tool.roles:
                allowed = "、".join(ROLE_LABELS.get(r, r) for r in tool.roles)
                result = {"error": f"当前角色（{ROLE_LABELS.get(user.role, user.role)}）无权执行该操作，"
                                    f"该操作权限为：{allowed}。请向用户说明，并建议其他可用的帮助。"}
                round_refs = []
            else:
                out = tool.executor(db, user, project, args)
                if isinstance(out, Terminal):
                    weekly_id = out.weekly_id
                    refs += out.refs
                    yield {"type": "refs", "refs": _dedupe_refs(refs)}
                    for piece in _chunk(out.text):
                        streamed_any = True
                        yield {"type": "delta", "text": piece}
                    yield {"type": "done", "weekly_id": weekly_id}
                    return
                result, round_refs = out

            refs += round_refs
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
