"""仅用 embedding 诊断固定检索问题；复用临时数据库和向量目录，不调用文本模型。"""
import argparse
import json
from pathlib import Path

from evaluate_rag import evaluate, load_cases


DIAGNOSTICS = [
    {"id": "helmet-raw", "type": "question", "query": "工人在工地干活时必须戴安全帽吗", "relevant": ["3.2.1"]},
    {"id": "helmet-neutral", "type": "question", "query": "施工现场 作业人员 安全帽 佩戴要求", "relevant": ["3.2.1"]},
    {"id": "helmet-rewritten", "type": "question", "query": "进入施工现场必须佩戴安全帽 个人防护用品 要求", "relevant": ["3.2.1"]},
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("keyword", "vector"), default="keyword")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.mode, load_cases() + DIAGNOSTICS)
    report["diagnostic_note"] = "3.2.1仅支持高处作业条件下的安全帽要求；检索命中不等于支持所有施工情形。"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["status"], flush=True)
    for variant, data in report.get("variants", {}).items():
        for row in data["cases"]:
            if row["id"].startswith("helmet-"):
                print(variant, row["id"], row["mode"], row["top10"], flush=True)


if __name__ == "__main__":
    main()
