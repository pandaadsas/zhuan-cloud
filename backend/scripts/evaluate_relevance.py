"""依据核验评测。标准答案仅用于本地评分；默认不运行任何外部模型。"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# 复用现有评测的导入连接隔离和临时 Chroma 生命周期。
from scripts.evaluate_rag import Base, settings, create_engine, Session, evaluation_directory, close_chroma
from app.agents import graph, assessor, llm
from app.rag import evidence, retriever
from app.services.knowledge import BUILTIN_MD_FILE, sync_builtin_knowledge
from tests.fixtures.relevance_cases import cases, REPORT_CASES


def answer(question, judgment, cfg):
    if judgment["status"] in ("unverified", "insufficient") or judgment.get("original"):
        return evidence.render_evidence(judgment)
    payload = evidence.answer_payload(judgment)
    try:
        resp = evidence.bounded_call(lambda: llm.client(cfg).with_options(timeout=20, max_retries=0).chat.completions.create(
            model=cfg.qwen_text_model, temperature=0.4,
            messages=[{"role": "system", "content": evidence.ANSWER_RULES + "使用中文，简洁回答。"},
                      {"role": "user", "content": json.dumps({"question": question, "evidence": payload}, ensure_ascii=False)}]), 20)
        return resp.choices[0].message.content
    except Exception:
        return evidence.render_evidence(judgment)


def evaluate_case(item, candidates, mode, cfg, remote):
    question = item["question"]
    start = time.perf_counter()
    baseline_context = "\n".join(f"《{r['doc_name']}》{r['clause_no']} {r['title']}：{r['content']}" for r in candidates)
    baseline_error = None
    try:
        baseline = evidence.bounded_call(lambda: llm.chat_text(
        "你是建筑工地安全知识助手，依据给定条款回答问题，并标注条款出处；检索不到的内容明确说明。120字以内。",
            f"问题：{question}\n检索条款：\n{baseline_context}"), 20) if remote and candidates else "未运行真实生成" if not remote else evidence.INSUFFICIENT_NOTICE
    except Exception as exc:
        baseline, baseline_error = None, type(exc).__name__
    baseline_ms = (time.perf_counter() - start) * 1000
    start = time.perf_counter()
    judgment = evidence.check_evidence(question, candidates, query=question, cfg=cfg)
    judge_ms = (time.perf_counter() - start) * 1000
    rendered = answer(question, judgment, cfg) if remote else evidence.render_evidence(judgment)
    refs = {r["clause_no"][1:-1] for r in judgment["accepted_refs"]}
    required = set(item["supporting_clauses"])
    return {**item, "retrieval_mode": mode, "candidates": candidates,
            "baseline": {"answer": baseline, "error": baseline_error, "candidate_refs": [evidence.ref_of(r) for r in candidates], "elapsed_ms": round(baseline_ms, 2)},
            "optimized": {"evidence": judgment, "answer": rendered, "judge_ms": round(judge_ms, 2),
                          "elapsed_ms": round((time.perf_counter() - start) * 1000, 2),
                          "state_correct": judgment["status"] == item["expected"],
                          "required_refs_covered": required <= refs},
            "semantic_review": None}


def summary(records):
    negative = [r for r in records if r["expected"] == "insufficient"]
    positive = [r for r in records if r["expected"] == "supported"]
    partial = [r for r in records if r["expected"] == "partial"]
    review_complete = all(r["semantic_review"] is not None for r in records)
    refs, invalid_refs, quotes, invalid_quotes = 0, 0, 0, 0
    for record in records:
        judgment = record["optimized"]["evidence"]
        candidates = judgment["candidates"]
        for ref in judgment["accepted_refs"]:
            refs += 1
            invalid_refs += not any(ref == evidence.ref_of(c) for c in candidates)
        for point in judgment["supported_points"]:
            for item in point["evidence"]:
                quotes += 1
                index = int(item["candidate_id"][1:]) - 1
                invalid_quotes += (not 0 <= index < len(candidates)
                                   or re.sub(r"\s+", "", item["quote"]) not in re.sub(r"\s+", "", candidates[index]["content"]))
    return {
        "count": len(records), "modes": dict(Counter(r["retrieval_mode"] for r in records)),
        "false_accepts": sum(r["optimized"]["evidence"]["status"] in ("supported", "partial") for r in negative),
        "false_rejects": sum(r["optimized"]["evidence"]["status"] != "supported" for r in positive),
        "partial_structurally_correct": sum(r["optimized"]["state_correct"] and r["optimized"]["required_refs_covered"] for r in partial),
        "unverified": sum(r["optimized"]["evidence"]["status"] == "unverified" for r in records),
        "judge_calls": sum(r["optimized"]["evidence"]["judge_calls"] for r in records),
        "accepted_ref_count": refs, "invalid_refs_accepted": invalid_refs,
        "accepted_quote_count": quotes, "invalid_quotes_accepted": invalid_quotes,
        "mean_judge_ms": statistics.mean(r["optimized"]["judge_ms"] for r in records) if records else None,
        "semantic_review_complete": review_complete,
        "baseline_candidate_false_hits": sum(bool(r["candidates"]) for r in negative),
        "baseline_generation_unverified": sum(not r["baseline"]["answer"] for r in records),
        "note": "候选命中不等同于生成误答；baseline答案、支持要点及partial覆盖需逐条语义复核"}


def apply_review(report: dict, review: dict) -> dict:
    """只评分已有结果，不发模型请求。复核绑定语料、样例、提示词和具体结果文件。"""
    if review.get("cases_sha256") != report["cases_sha256"] or review.get("judge_prompt_sha256") != report["judge_prompt_sha256"]:
        raise ValueError("复核与样例/提示词版本不一致")
    rows = review.get("qa", {})
    if set(rows) != {r["id"] for r in report.get("records", [])}:
        raise ValueError("必须逐条复核本次全部问答结果")
    for record in report["records"]:
        row = rows[record["id"]]
        for field in ("supported_points_valid", "unsupported_points_complete", "answer_grounded", "baseline_unsupported_claim"):
            if not isinstance(row.get(field), bool):
                raise ValueError("语义复核需要明确布尔评分")
        if not row.get("notes"):
            raise ValueError("语义复核缺少说明")
        record["semantic_review"] = row
    report_rows = review.get("reports", {})
    if set(report_rows) != {r["id"] for r in report.get("reports", [])}:
        raise ValueError("必须逐条复核全部上报结果")
    for record in report.get("reports", []):
        row = report_rows[record["id"]]
        if not isinstance(row.get("grounded"), bool) or not row.get("notes"):
            raise ValueError("上报复核缺少评分或说明")
        record["semantic_review"] = row
    report["summary"] = summary(report["records"])
    accept = [r for r in report["records"] if r["split"] == "acceptance"]
    partial_correct = sum(r["optimized"]["state_correct"] and r["optimized"]["required_refs_covered"]
                          and all(r["semantic_review"][f] for f in ("supported_points_valid", "unsupported_points_complete", "answer_grounded"))
                          for r in accept if r["expected"] == "partial")
    full_correct = sum(r["optimized"]["state_correct"] and r["optimized"]["required_refs_covered"]
                       and r["semantic_review"]["supported_points_valid"] and r["semantic_review"]["answer_grounded"]
                       for r in accept if r["expected"] == "supported")
    accept_summary = summary(accept)
    report["acceptance"] = {**accept_summary, "partial_semantically_correct": partial_correct, "fully_supported_correct": full_correct}
    report["baseline_unsupported_answers"] = sum(r["semantic_review"]["baseline_unsupported_claim"] for r in report["records"])
    report["optimized_ungrounded_answers"] = sum(not r["semantic_review"]["answer_grounded"] for r in report["records"])
    report["reviewer"] = review.get("reviewer", "unspecified")
    report["domain_expert_reviewed"] = bool(review.get("domain_expert_reviewed", False))
    complete_acceptance = Counter(r["category"] for r in accept) == {"supported": 10, "partial": 10, "unrelated": 10, "missing": 10}
    reports_passed = len(report.get("reports", [])) == 12 and all(r["behavior_passed"] and r["semantic_review"]["grounded"] for r in report["reports"])
    report["enable_gate_passed"] = (report["remote"] and report["mode"] == "vector" and complete_acceptance
                                     and all(r["retrieval_mode"] in ("vector", "hybrid") for r in report["records"])
                                     and all(r["retrieval_mode"] in ("vector", "hybrid") for r in report.get("reports", []))
                                     and accept_summary["false_accepts"] <= 1 and full_correct >= 9 and partial_correct >= 9
                                     and report["summary"]["invalid_refs_accepted"] == 0 and report["summary"]["invalid_quotes_accepted"] == 0
                                     and report["optimized_ungrounded_answers"] == 0 and reports_passed)
    report["status"] = "reviewed_passed" if report["enable_gate_passed"] else "reviewed_not_passed" if accept else "reviewed_development"
    return report


def evaluate_reports(db, cfg, remote, on_record=None):
    records = []
    for case in REPORT_CASES:
        query = graph.build_report_query(case["text"], {"building": "3号楼", "floor": "12层", "hazard_type": case["hazard_type"]})
        regs, mode = retriever.search_with_mode(db, query, 4)
        start = time.perf_counter()
        baseline_error = None
        try:
            baseline = evidence.bounded_call(lambda: assessor.build_suggestion({"description": case["text"], "hazard_type": case["hazard_type"], "risk_level": "高"}, regs), 20) if remote else "未运行真实生成"
        except Exception as exc:
            baseline, baseline_error = None, type(exc).__name__
        holder = []
        def judge(*args, **kw):
            result = evidence.check_evidence(*args, cfg=cfg, **kw)
            holder.append(result)
            return result
        with ExitStack() as stack:
            stack.enter_context(patch.object(graph, "evidence_enabled", return_value=True))
            stack.enter_context(patch.object(graph, "kb_search", return_value=regs))
            stack.enter_context(patch.object(graph, "check_evidence", side_effect=judge))
            stack.enter_context(patch.object(graph, "extract_hazard", return_value={"building": "3号楼", "floor": "12层", "hazard_type": case["hazard_type"], "risk_level": "高", "description": case["text"]}))
            stack.enter_context(patch.object(graph, "match_responsible", return_value={"primary_user_id": 7}))
            original_chat = assessor.chat_text
            def bounded_chat(*args):
                try:
                    return evidence.bounded_call(lambda: original_chat(*args), 20)
                except TimeoutError:
                    return None
            stack.enter_context(patch.object(assessor, "chat_text", side_effect=bounded_chat))
            if case.get("force_failure"):
                stack.enter_context(patch.object(evidence, "client", side_effect=TimeoutError))
            draft = graph.process_report(db, case["text"], "text")["order_draft"]
        judgment = holder[0]
        safe_failure = not draft["regulation_refs"] and "规范依据待人工核实" in draft["suggestion"]
        required_refs = {f"第{n}条" for n in case["clauses"]}
        accepted_refs = {r["clause_no"] for r in draft["regulation_refs"]}
        records.append({**case, "retrieval_mode": mode, "baseline_suggestion": baseline, "baseline_error": baseline_error,
                        "evidence": judgment, "draft": draft,
                        "behavior_passed": judgment["status"] == case["expected"] and (safe_failure if case["expected"] in ("insufficient", "unverified") else bool(draft["regulation_refs"]))
                                           and required_refs <= accepted_refs
                                           and draft["risk_level"] == "高" and draft["responsible_user_id"] == 7,
                        "elapsed_ms": round((time.perf_counter() - start) * 1000, 2), "semantic_review": None})
        print(f"已完成上报 {case['id']}：{judgment['status']}", flush=True)
        if on_record:
            on_record(records)
    return records


def run(args):
    all_cases = cases()
    qa = [c for c in all_cases if args.split == "all" or c["split"] == args.split]
    cfg = SimpleNamespace(**settings.model_dump())
    cfg.rag_evidence_check_enabled = True
    remote = args.remote
    if not remote:
        cfg.mock_mode = True
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "split": args.split,
              "corpus_sha256": hashlib.sha256(BUILTIN_MD_FILE.read_bytes()).hexdigest(),
              "cases_sha256": hashlib.sha256(json.dumps(all_cases, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
              "judge_prompt_sha256": hashlib.sha256(evidence.JUDGE_PROMPT.encode()).hexdigest(),
              "answer_rules_sha256": hashlib.sha256(evidence.ANSWER_RULES.encode()).hexdigest(),
              "report_prompt_sha256": hashlib.sha256(assessor.ASSESS_SYSTEM_PROMPT.encode()).hexdigest(),
              "report_cases_sha256": hashlib.sha256(json.dumps(REPORT_CASES, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
              "text_model": cfg.qwen_text_model, "embedding_model": cfg.qwen_embed_model,
              "remote": remote, "mode": args.mode, "enable_gate_passed": False,
              "judge_options": {"timeout_seconds": 20, "max_retries": 0, "temperature": 0, "enable_thinking": False},
              "generation_evaluation_timeout_seconds": 20,
              "evaluation_path": "共享依据核验+相同回答约束的生成；真实Agent工具与SSE接入另由集成测试验证"}
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with evaluation_directory() as directory, Session(engine) as db, ExitStack() as stack:
        stack.enter_context(patch.object(retriever, "CHROMA_DIR", directory))
        stack.enter_context(patch.object(retriever, "_cache", []))
        stack.enter_context(patch.object(retriever, "_col", None))
        stack.callback(close_chroma)
        for module in (retriever, evidence, llm):
            stack.enter_context(patch.object(module, "get_cfg", return_value=cfg))
        if args.mode == "keyword":
            stack.enter_context(patch.object(retriever, "llm_ready", return_value=False))
            stack.enter_context(patch.object(retriever, "embed_texts", return_value=None))
        sync_builtin_knowledge(db)
        sync_mode = retriever.refresh_cache(db)
        if args.mode == "vector" and sync_mode != "vector":
            report.update(status="unverified", reason="向量同步失败或缺少真实配置；未运行模型评测")
        else:
            # 顺序检索，避免SQLAlchemy会话被跨线程使用；模型判断和生成可独立并发。
            inputs = [(c, *retriever.search_with_mode(db, c["question"], 3)) for c in qa]
            with ThreadPoolExecutor(max_workers=4 if remote else 1) as pool:
                futures = [pool.submit(evaluate_case, c, regs, mode, cfg, remote) for c, regs, mode in inputs]
                records = []
                for i, future in enumerate(futures, 1):
                    records.append(future.result())
                    if i % 10 == 0:
                        print(f"已完成 {i}/{len(inputs)} 条规范问答", flush=True)
            report["records"] = records
            report["summary"] = summary(records)
            def save_progress(report_records):
                report.update(reports=report_records, status="evaluating_reports")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.reports:
                save_progress([])
            report["reports"] = evaluate_reports(db, cfg, remote, save_progress) if args.reports else []
            valid_remote = remote and not cfg.mock_mode and bool(cfg.dashscope_api_key)
            allowed_modes = ("vector", "hybrid") if args.mode == "vector" else ("keyword",)
            report["status"] = "evaluated_pending_semantic_review" if valid_remote and all(r["retrieval_mode"] in allowed_modes for r in records) else "unverified"
    engine.dispose()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true", help="允许将固定合成问题和规范文本发送至项目配置的DashScope接口")
    parser.add_argument("--mode", choices=("keyword", "vector"), default="keyword")
    parser.add_argument("--split", choices=("development", "acceptance", "all"), default="development")
    parser.add_argument("--reports", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-input", type=Path, help="复核已有报告，不调用模型")
    parser.add_argument("--review", type=Path, help="独立逐条语义复核文件")
    args = parser.parse_args()
    if args.review_input:
        if not args.review:
            parser.error("--review-input 必须同时提供 --review")
        report = json.loads(args.review_input.read_text(encoding="utf-8"))
        review = json.loads(args.review.read_text(encoding="utf-8"))
        if review.get("report_sha256") != hashlib.sha256(args.review_input.read_bytes()).hexdigest():
            raise ValueError("复核不是针对指定的具体报告")
        report = apply_review(report, review)
    else:
        report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("records", "reports")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
