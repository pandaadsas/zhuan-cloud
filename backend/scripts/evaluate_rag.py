"""隔离评测：python scripts/evaluate_rag.py --mode both --output ../docs/RAG轻量优化评测.json"""
import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import shutil
import sys
import time
import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# database.py 有导入即连接的副作用；仅在导入期间将其 engine 替换为内存库。
# 不连接业务数据库，不读取设置页配置；AI 配置仅来自环境变量 / backend/.env。
with patch("sqlalchemy.create_engine", side_effect=lambda *a, **kw: create_engine("sqlite:///:memory:")):
    from app.database import Base
    from app.config import settings
    from app.agents.graph import build_report_query
    from app.rag import retriever
    from app.services.knowledge import BUILTIN_MD_FILE, parse_regulation_md, sync_builtin_knowledge


CASES = BACKEND / "tests" / "fixtures" / "rag_cases.json"


@contextmanager
def evaluation_directory():
    # Python 3.14 TemporaryDirectory 的 Windows 私有 ACL 在受限执行账户下不可读。
    # 使用普通目录权限，仍为随机、独立、用后清理的 workspace 临时目录。
    directory = BACKEND / (".rag-eval-" + uuid.uuid4().hex)
    directory.mkdir(mode=0o777)
    try:
        yield directory
    finally:
        if directory.resolve().parent != BACKEND.resolve():
            raise ValueError("临时目录不在 backend 内")
        shutil.rmtree(directory)


def close_chroma():
    if retriever._col is not None:
        from chromadb.api.client import SharedSystemClient
        retriever._col._client._system.stop()
        SharedSystemClient.clear_system_cache()
        retriever._col = None


def load_cases():
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    expected = {"report": 20, "question": 10, "number": 5, "out_of_scope": 5}
    if Counter(c["type"] for c in cases) != expected or len({c["id"] for c in cases}) != 40:
        raise ValueError("评测样例数量、类型或 ID 不符合约定")
    return cases


def retrieval_metrics(expected, results):
    expected = set(expected)
    returned = [r["clause_no"].removeprefix("第").removesuffix("条") for r in results]
    if not expected:
        return None, None
    recall = len(expected & set(returned)) / len(expected)
    rr = next((1 / rank for rank, number in enumerate(returned, 1) if number in expected), 0)
    return recall, rr


def baseline_search(db, query, k):
    """冻结本轮修改前 search 的行为；共用未改动的向量和字符召回函数。"""
    if not retriever._cache:
        retriever.refresh_cache(db)
    if not retriever._cache:
        return [], "empty"
    try:
        results = retriever._search_vector(query, k)
    except Exception:
        results = []
    return (results, "vector") if results else (retriever._search_keyword(query, k), "keyword")


def aggregate(records):
    groups = {}
    for kind in ("report", "question", "number", "out_of_scope"):
        rows = [r for r in records if r["type"] == kind]
        positive = [r for r in rows if r["recall"] is not None]
        groups[kind] = {
            "count": len(rows),
            "recall": statistics.mean(r["recall"] for r in positive) if positive else None,
            "mrr": statistics.mean(r["rr"] for r in positive) if positive else None,
            "negative_false_hits": sum(bool(r["returned"]) for r in rows if not r["relevant"]),
            "modes": dict(Counter(r["mode"] for r in rows)),
            "mean_ms": statistics.mean(r["elapsed_ms"] for r in rows),
        }
    return groups


def evaluate(mode, cases):
    if mode == "vector" and (settings.mock_mode or not settings.dashscope_api_key):
        return {"status": "unverified", "reason": "环境变量/.env 未启用真实 AI 或缺少 Key；设置页配置不用于隔离评测"}
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    original_embed = retriever.embed_texts
    embed_cache = {}

    def cached_embed(texts):
        key = tuple(texts)
        if key not in embed_cache:
            value = original_embed(texts)
            if value:
                embed_cache[key] = value
            return value
        return embed_cache[key]

    with evaluation_directory() as directory, Session(engine) as db, ExitStack() as stack:
        stack.enter_context(patch.object(retriever, "CHROMA_DIR", Path(directory)))
        stack.enter_context(patch.object(retriever, "get_cfg", return_value=settings))
        stack.enter_context(patch("app.agents.llm.get_cfg", return_value=settings))
        stack.enter_context(patch.object(retriever, "_cache", []))
        stack.enter_context(patch.object(retriever, "_col", None))
        if mode == "keyword":
            stack.enter_context(patch.object(retriever, "llm_ready", return_value=False))
            stack.enter_context(patch.object(retriever, "embed_texts", return_value=None))
        else:
            stack.enter_context(patch.object(retriever, "embed_texts", side_effect=cached_embed))
        sync_builtin_knowledge(db)
        corpus_numbers = {r["clause_no"].removeprefix("第").removesuffix("条")
                          for r in parse_regulation_md(
                              BUILTIN_MD_FILE.read_text(encoding="utf-8"))}
        for case in cases:
            if not set(case["relevant"]) <= corpus_numbers:
                raise ValueError(f"{case['id']} 标注了不存在的条款")
        sync_mode = retriever.refresh_cache(db)
        if mode == "vector" and sync_mode != "vector":
            close_chroma()
            db.close()
            engine.dispose()
            return {"status": "unverified", "sync_mode": sync_mode,
                    "query_enable_gate_passed": False,
                    "reason": "向量同步失败；停止真实模式评测，不用字符降级结果替代向量验收"}
        variants = {}
        for variant in ("baseline", "optimized_raw", "candidate_query"):
            records = []
            for case in cases:
                query = case["query"]
                if variant == "candidate_query" and case["type"] == "report":
                    query = build_report_query(query, case["extracted"])
                start = time.perf_counter()
                search = baseline_search if variant == "baseline" else retriever.search_with_mode
                results, actual_mode = search(db, query, 10)
                elapsed = (time.perf_counter() - start) * 1000
                k = 4 if case["type"] == "report" else 3
                recall, rr = retrieval_metrics(case["relevant"], results[:k])
                returned = [r["clause_no"] for r in results[:k]]
                top10 = [r["clause_no"] for r in results]
                expected = {f"第{n}条" for n in case["relevant"]}
                if not expected:
                    failure = "拒答校准候选" if returned else None
                elif recall < 1:
                    failure = "rerank候选" if expected <= set(top10) else "术语/语义漏召回，混合检索候选"
                else:
                    failure = None
                records.append({**case, "effective_query": query, "k": k, "mode": actual_mode,
                                "returned": returned, "top10": top10, "recall": recall, "rr": rr,
                                "elapsed_ms": round(elapsed, 3), "failure_category": failure})
            variants[variant] = {"metrics": aggregate(records), "cases": records}
        raw = variants["optimized_raw"]["metrics"]["report"]
        candidate = variants["candidate_query"]["metrics"]["report"]
        semantic = [r for v in variants.values() for r in v["cases"] if r["type"] in ("report", "question")]
        verified = mode == "vector" and sync_mode == "vector" and all(r["mode"] in ("vector", "hybrid") for r in semantic)
        passes = (candidate["recall"] >= raw["recall"] and candidate["mrr"] >= raw["mrr"]
                  and (candidate["recall"] > raw["recall"] or candidate["mrr"] > raw["mrr"]))
        result = {"status": "verified" if mode == "keyword" or verified else "unverified",
                  "sync_mode": sync_mode, "query_metric_gate_passed": passes,
                  "query_enable_gate_passed": verified and passes, "variants": variants,
                  "latency_note": "包含Top-10诊断检索；向量复用query embedding，延迟非冷请求基准"}
        if mode == "vector" and not verified:
            result["reason"] = "向量同步或语义查询发生降级，不能作为真实模式验收"
        # Chroma 的系统注册表会持有 Windows 文件句柄；在临时目录清理前释放。
        close_chroma()
    engine.dispose()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("keyword", "vector", "both"), default="both")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = load_cases()
    modes = ("keyword", "vector") if args.mode == "both" else (args.mode,)
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "corpus_sha256": hashlib.sha256(BUILTIN_MD_FILE.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "embedding_model": settings.qwen_embed_model,
        "annotation_note": "标注由实现者逐条核对仓库规范原文，尚未经领域专家独立复核；不是外部泛化评测集",
        "results": {mode: evaluate(mode, cases) for mode in modes},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({m: {k: v for k, v in r.items() if k != "variants"} for m, r in report["results"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
