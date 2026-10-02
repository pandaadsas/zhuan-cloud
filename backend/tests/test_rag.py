import json
from pathlib import Path
import unittest
from unittest.mock import patch

from app.agents import assessor, graph
from app.rag import retriever
from app.services.knowledge import BUILTIN_MD_FILE, parse_regulation_md


def entry(number, content="完整正文", row_id=1, doc="规范"):
    return {"id": row_id, "doc_name": doc, "clause_no": f"第{number}条",
            "title": "章节", "content": content, "tags": [], "grams": retriever._bigrams(content)}


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(retriever, "_cache", [entry("3.2.3"), entry("3.10.5", row_id=2)])
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_exact_formats_and_no_api(self):
        with patch.object(retriever, "_search_vector") as vector:
            for query in ("3.2.3", "第3.2.3条", "请查3.2.3", "GB 55034-2022第3.2.3条"):
                results, mode = retriever.search_with_mode(None, query)
                self.assertEqual(mode, "exact")
                self.assertEqual([r["clause_no"] for r in results], ["第3.2.3条"])
                self.assertEqual(results[0]["score"], 1.0)
                self.assertEqual(results[0]["content"], "完整正文")
            vector.assert_not_called()

    def test_exact_order_dedup_limit_and_missing(self):
        query = "3.10.5与第99.99.99条、3.2.3、3.10.5"
        self.assertEqual([r["clause_no"] for r in retriever.search(None, query)], ["第3.10.5条", "第3.2.3条"])
        self.assertEqual(len(retriever.search(None, query, k=1)), 1)
        with patch.object(retriever, "_search_vector") as vector:
            self.assertEqual(retriever.search(None, "第99.99.99条"), [])
            vector.assert_not_called()

    def test_duplicate_number_stable_ids(self):
        retriever._cache = [entry("3.2.3", row_id=9, doc="B"), entry("3.2.3", row_id=2, doc="A")]
        self.assertEqual([r["doc_name"] for r in retriever.search(None, "3.2.3")], ["A", "B"])

    def test_year_version_not_clause(self):
        for query in ("GB 55034-2022", "版本3.2.3.4", "v3.2.3", "3.2.30.4"):
            self.assertEqual(retriever._clause_numbers(query), [])

    def test_empty_does_not_refresh(self):
        with patch.object(retriever, "_cache", []), patch.object(retriever, "refresh_cache") as refresh:
            self.assertEqual(retriever.search(None, " \n\t"), [])
            self.assertEqual(retriever.search(None, "防护", k=0), [])
            refresh.assert_not_called()

    def test_vector_exception_and_empty_fallback(self):
        for behavior in ({"side_effect": RuntimeError("failed")}, {"return_value": []}):
            with patch.object(retriever, "_search_vector", **behavior):
                results, mode = retriever.search_with_mode(None, "完整正文")
                self.assertTrue(results)
                self.assertEqual(mode, "keyword")

    def test_vector_success_no_keyword(self):
        result = [{"clause_no": "第3.2.3条"}]
        with patch.object(retriever, "_search_vector", return_value=result), patch.object(retriever, "_search_keyword") as keyword:
            self.assertEqual(retriever.search_with_mode(None, "防护"), (result, "vector"))
            keyword.assert_not_called()


class QueryTest(unittest.TestCase):
    def test_preserve_facts_and_no_description_compression(self):
        raw = "3号楼12层东侧护栏不足1.2m，未防护，不得继续作业，积水0.8m"
        query = graph.build_report_query(raw, {"building": "3号楼", "floor": "12层", "hazard_type": "高处作业-临边防护", "description": "短描述"})
        self.assertTrue(query.startswith("高处作业 临边防护 "))
        for fact in ("东侧", "1.2m", "未防护", "不得继续作业", "0.8m"):
            self.assertIn(fact, query)
        self.assertNotIn("3号楼", query)
        self.assertNotIn("12层", query)

    def test_no_partial_location_removal_and_empty_fallback(self):
        ext = {"building": "3号楼", "floor": "2层", "hazard_type": "其他-待归类"}
        self.assertEqual(graph.build_report_query("13号楼12层", ext), "13号楼12层")
        self.assertEqual(graph.build_report_query("3号楼2层", ext), "3号楼2层")

    def test_pipeline_query_gate(self):
        raw = "3号楼12层临边未防护"
        ext = {"building": "3号楼", "floor": "12层", "hazard_type": "高处作业-临边防护", "risk_level": "高"}
        for enabled in (False, True):
            with patch.object(graph, "REPORT_QUERY_OPTIMIZATION_ENABLED", enabled), patch.object(graph, "extract_hazard", return_value=ext), patch.object(graph, "kb_search", return_value=[]) as search, patch.object(graph, "build_suggestion", return_value="建议"), patch.object(graph, "match_responsible", return_value={}):
                result = graph.process_report(None, raw, "text")
                expected = graph.build_report_query(raw, ext) if enabled else raw
                search.assert_called_once_with(None, expected, k=4)
                self.assertEqual(result["order_draft"]["risk_level"], "高")


class ContextTest(unittest.TestCase):
    def test_real_clause_after_80_chars_reaches_llm(self):
        clause = next(r for r in parse_regulation_md(BUILTIN_MD_FILE.read_text(encoding="utf-8")) if r["clause_no"] == "第3.10.5条")
        self.assertIn("严禁预约停送电", clause["content"][80:])
        reg = dict(clause, doc_name="规范")
        with patch.object(assessor, "chat_text", return_value="建议") as chat:
            assessor.build_suggestion({"description": "带电检修", "risk_level": "高"}, [reg])
            prompt, context = chat.call_args.args
            self.assertIn(clause["content"], context)
            self.assertIn("依据不足", prompt)

    def test_budget_and_top_three_whole_clauses(self):
        regs = [entry("3.2.1", "A" * 8100), entry("3.2.2", "B" * 7900), entry("3.2.3", "C" * 200), entry("3.2.4", "D")]
        with self.assertLogs("zhuan.assessor", level="WARNING"):
            context = assessor.build_regulation_context(regs)
        self.assertLessEqual(len(context), 8000)
        self.assertIn("B" * 7900, context)
        self.assertNotIn("A", context)
        self.assertNotIn("C", context)
        self.assertNotIn("第3.2.4条", context)

    def test_exact_budget_boundary(self):
        reg = entry("3.2.1", "")
        overhead = len(assessor.build_regulation_context([reg]))
        reg["content"] = "X" * (8000 - overhead)
        self.assertEqual(len(assessor.build_regulation_context([reg])), 8000)


class FixtureTest(unittest.TestCase):
    def test_annotation_counts_and_existing_numbers(self):
        from collections import Counter
        cases = json.loads((Path(__file__).parent / "fixtures" / "rag_cases.json").read_text(encoding="utf-8"))
        self.assertEqual(Counter(c["type"] for c in cases), {"report": 20, "question": 10, "number": 5, "out_of_scope": 5})
        numbers = {r["clause_no"][1:-1] for r in parse_regulation_md(BUILTIN_MD_FILE.read_text(encoding="utf-8"))}
        for case in cases:
            self.assertTrue(set(case["relevant"]) <= numbers)


class EvaluationTest(unittest.TestCase):
    def test_metrics_multiple_relevant_and_negative(self):
        from scripts.evaluate_rag import retrieval_metrics
        results = [{"clause_no": "第3.2.1条"}, {"clause_no": "第3.2.3条"}]
        self.assertEqual(retrieval_metrics(["3.2.3", "3.10.5"], results), (0.5, 0.5))
        self.assertEqual(retrieval_metrics([], results), (None, None))

    def test_keyword_evaluation_never_enables_vector_gate(self):
        from scripts.evaluate_rag import evaluate, load_cases
        with patch.object(retriever, "embed_texts") as embed:
            result = evaluate("keyword", load_cases())
            embed.assert_not_called()
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["query_enable_gate_passed"])
        exact = result["variants"]["optimized_raw"]["cases"]
        for case in (r for r in exact if r["type"] == "number"):
            self.assertEqual(case["mode"], "exact")
            self.assertEqual([n[1:-1] for n in case["returned"]], case["relevant"])

    def test_vector_sync_failure_stops_before_queries(self):
        from scripts import evaluate_rag
        with patch.object(evaluate_rag.settings, "mock_mode", False), patch.object(evaluate_rag.settings, "dashscope_api_key", "test-key"), patch.object(retriever, "refresh_cache", return_value="keyword"), patch.object(retriever, "_search_vector") as search:
            result = evaluate_rag.evaluate("vector", evaluate_rag.load_cases())
        self.assertEqual(result["status"], "unverified")
        self.assertFalse(result["query_enable_gate_passed"])
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
