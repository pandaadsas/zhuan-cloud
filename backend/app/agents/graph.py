"""LangGraph 隐患处置流水线：

上报文本 → 信息抽取 → (缺信息?追问) → 知识库检索 → 风险定级+处置建议 → 责任匹配 → 工单草稿(待审核)

状态机即业务流程，节点可独立替换（规则引擎/LLM引擎），答辩可讲可演示。
"""
import logging
from datetime import datetime, timedelta
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from ..rag.retriever import search as kb_search
from .assessor import build_suggestion, deadline_days, finalize_risk
from .dispatcher import match_responsible
from .extractor import extract_hazard, need_clarify

logger = logging.getLogger("zhuan.graph")


class PipelineState(TypedDict, total=False):
    raw_text: str
    source_type: str
    extracted: dict
    regs: list
    risk: str
    suggestion: str
    responsible: dict
    order_draft: dict
    need_clarify: bool
    question: str


def _node_extract(state: PipelineState) -> PipelineState:
    return {"extracted": extract_hazard(state["raw_text"])}


def _node_clarify(state: PipelineState) -> PipelineState:
    return {
        "need_clarify": True,
        "question": "请补充隐患的具体位置（如：3号楼12层东侧临边）和问题类型，以便AI生成整改工单。",
    }


def _route_after_extract(state: PipelineState) -> str:
    return "clarify" if need_clarify(state["extracted"]) else "retrieve"


def build_pipeline(db: Session, project_id: int | None = None):
    def node_retrieve(state: PipelineState) -> PipelineState:
        return {"regs": kb_search(db, state["raw_text"], k=4)}

    def node_assess(state: PipelineState) -> PipelineState:
        risk = finalize_risk(state["extracted"])
        extracted = dict(state["extracted"], risk_level=risk)
        suggestion = build_suggestion(extracted, state["regs"])
        return {"risk": risk, "extracted": extracted, "suggestion": suggestion}

    def node_dispatch(state: PipelineState) -> PipelineState:
        return {"responsible": match_responsible(db, state["extracted"], project_id=project_id)}

    def node_draft(state: PipelineState) -> PipelineState:
        ext, resp = state["extracted"], state["responsible"]
        building = ext.get("building", "")
        floor = ext.get("floor", "")
        head = " ".join(x for x in (building, floor) if x)
        title = f"{head} {ext.get('hazard_type', '安全隐患')}隐患".strip()
        refs = [
            {"doc_name": r["doc_name"], "clause_no": r["clause_no"], "title": r["title"]}
            for r in state["regs"][:4]
        ]
        draft = {
            "title": title,
            "building": building,
            "floor": floor,
            "spot": ext.get("spot", ""),
            "hazard_type": ext.get("hazard_type", ""),
            "description": ext.get("description", ""),
            "risk_level": state["risk"],
            "suggestion": state["suggestion"],
            "regulation_refs": refs,
            "source_type": state.get("source_type", "text"),
            "extraction_engine": ext.get("engine", ""),
            "responsible_user_id": resp.get("primary_user_id"),
            "responsible_name": resp.get("primary_name", ""),
            "match_reason": resp.get("reason", ""),
            "alternates": resp.get("alternates", []),
            "deadline": (datetime.now() + timedelta(days=deadline_days(state["risk"]))).isoformat(
                sep=" ", timespec="minutes"
            ),
        }
        return {"order_draft": draft, "need_clarify": False}

    g = StateGraph(PipelineState)
    g.add_node("extract", _node_extract)
    g.add_node("clarify", _node_clarify)
    g.add_node("retrieve", node_retrieve)
    g.add_node("assess", node_assess)
    g.add_node("dispatch", node_dispatch)
    g.add_node("draft", node_draft)
    g.set_entry_point("extract")
    g.add_conditional_edges("extract", _route_after_extract, {"clarify": "clarify", "retrieve": "retrieve"})
    g.add_edge("clarify", END)
    g.add_edge("retrieve", "assess")
    g.add_edge("assess", "dispatch")
    g.add_edge("dispatch", "draft")
    g.add_edge("draft", END)
    return g.compile()


def process_report(db: Session, raw_text: str, source_type: str = "text", project_id: int | None = None) -> dict:
    """跑完整流水线，返回结果（不落库，由路由层持久化）。"""
    app = build_pipeline(db, project_id=project_id)
    final = app.invoke({"raw_text": raw_text, "source_type": source_type})
    return {
        "need_clarify": final.get("need_clarify", False),
        "question": final.get("question", ""),
        "extracted": final.get("extracted", {}),
        "regs": final.get("regs", []),
        "order_draft": final.get("order_draft"),
    }
