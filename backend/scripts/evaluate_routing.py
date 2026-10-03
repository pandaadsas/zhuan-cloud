"""路由评测：仅发送固定合成消息和工具说明，不执行工具或读取业务记录。"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import statistics
import time
from types import SimpleNamespace
from unittest.mock import patch

from evaluate_rag import settings  # 导入阶段隔离业务数据库
from app.agents import chat_agent
from app.rag.evidence import bounded_call
from tests.fixtures.routing_cases import cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = cases()
    report = {"case_count": len(rows), "mode": "not_verified", "records": []}
    if args.remote and settings.dashscope_api_key and not settings.mock_mode:
        cfg = SimpleNamespace(dashscope_api_key=settings.dashscope_api_key, qwen_text_model=settings.qwen_text_model, rag_evidence_check_enabled=True)
        with patch.object(chat_agent, "get_cfg", return_value=cfg):
            prompt = chat_agent._system_prompt(SimpleNamespace(name="评测用户", role="safety_officer"), SimpleNamespace(name="合成评测项目"))
        # 还原修改前的首轮提示和工具集合；旧代码在无工具时强制 search_regulations。
        baseline_prompt = prompt[:prompt.index("0. 首轮")] + prompt[prompt.index("1. 涉及"):]
        sdk = chat_agent.client(cfg).with_options(timeout=20, max_retries=0)

        def evaluate(item):
            row, baseline = item
            start = time.perf_counter()
            messages = [{"role": "system", "content": baseline_prompt if baseline else prompt}, *row["history"], {"role": "user", "content": row["question"]}]
            schemas = [t.schema for t in chat_agent.TOOLS if not baseline or t.name not in chat_agent.CONVERSATION_TOOLS]
            result = {**row, "version": "baseline" if baseline else "optimized", "model_calls": 1}
            try:
                parts, slots, error = bounded_call(lambda: chat_agent._stream_llm_round(cfg, messages, schemas), 25)
                if error:
                    raise RuntimeError("model_request_failed")
                names = [s["name"] for s in slots.values()]
                if baseline and not names:
                    names = ["search_regulations"]
                valid = bool(names)
                for slot in slots.values():
                    parsed = json.loads(slot["arguments"] or "{}")
                    valid = valid and slot["name"] in {s["function"]["name"] for s in schemas} and isinstance(parsed, dict)
                    if slot["name"] in chat_agent.CONVERSATION_TOOLS:
                        valid = valid and len(slots) == 1 and set(parsed) == {"text"} and isinstance(parsed.get("text"), str) and bool(parsed["text"].strip())
                    if slot["name"] == "search_regulations":
                        valid = valid and isinstance(parsed.get("query"), str) and bool(parsed["query"].strip())
                result.update(tools=names, slots=slots, content="".join(parts), valid=bool(valid), correct=bool(valid) and len(names) == 1 and names[0] in row["expected"])
            except Exception as exc:
                result.update(tools=[], valid=False, correct=False, error=type(exc).__name__)
            result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return result

        with patch.object(chat_agent, "client", return_value=sdk), ThreadPoolExecutor(max_workers=3) as pool:
            for record in pool.map(evaluate, [(row, baseline) for row in rows for baseline in (True, False)]):
                report["records"].append(record)
                print(record["id"], record["version"], record["tools"], record["correct"], flush=True)
        report.update(mode="real_model_first_route_only", model=cfg.qwen_text_model,
                      status="unverified" if any("error" in r for r in report["records"]) else "evaluated_pending_output_review")
        report["summary"] = {}
        for version in ("baseline", "optimized"):
            records = [r for r in report["records"] if r["version"] == version]
            needed = [r for r in records if "error" not in r and r["expected"] == ["search_regulations"]]
            unneeded = [r for r in records if "error" not in r and "search_regulations" not in r["expected"]]
            business = [r for r in records if "error" not in r and r["group"] == "business"]
            report["summary"][version] = {"correct": sum(r["correct"] for r in records), "count": len(records), "errors": sum("error" in r for r in records), "unnecessary_retrieval": sum("search_regulations" in r["tools"] for r in unneeded), "unnecessary_denominator": len(unneeded), "missed_retrieval": sum("search_regulations" not in r["tools"] for r in needed), "required_denominator": len(needed), "business_correct": sum(r["correct"] for r in business), "business_count": len(business), "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in records), 2)}
    else:
        report["reason"] = "需要 --remote、非模拟模式和文本模型配置；本次未验证真实路由"
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
