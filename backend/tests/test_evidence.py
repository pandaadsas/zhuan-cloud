import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from threading import Event

from app.agents import assessor, chat_agent, chat_tools, graph
from app.rag import evidence
from app.routers.chat import _rule_fallback
from tests.fixtures.relevance_cases import cases, REPORT_CASES


REG = {"doc_name": "测试规范", "clause_no": "第3.9.3条", "title": "中毒和窒息",
       "content": "受限或密闭空间作业前，应按照氧气、可燃性气体、有毒有害气体的顺序进行气体检测。", "tags": [], "score": 0.8}
CFG = SimpleNamespace(mock_mode=False, dashscope_api_key="test", qwen_text_model="test", rag_evidence_check_enabled=True)


def raw(status="supported"):
    return {"status": status, "supported_points": [{"text": "先检测氧气", "evidence": [{"candidate_id": "C1", "quote": "按照氧气、可燃性气体、有毒有害气体的顺序进行气体检测"}]}],
            "unsupported_points": ["仪器型号"] if status == "partial" else [], "accepted_refs": ["C1"], "reason": "条款支持检测顺序"}


def response(value):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value, ensure_ascii=False)))])


class JudgmentTest(unittest.TestCase):
    def test_valid_partial_and_refs(self):
        result = evidence.validate_judgment(raw("partial"), [REG])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["accepted_refs"], [evidence.ref_of(REG)])

    def test_invalid_quotes_ids_and_schema(self):
        for mutation in ("quote", "id", "refs", "status", "points", "missing"):
            value = raw()
            if mutation == "quote":
                value["supported_points"][0]["evidence"][0]["quote"] = "要求检测仪必须采用ABC型号"
            elif mutation == "id":
                value["supported_points"][0]["evidence"][0]["candidate_id"] = "C99"
            elif mutation == "refs":
                value["accepted_refs"] = ["C2"]
            elif mutation == "status":
                value["status"] = "approved"
            elif mutation == "points":
                value["supported_points"] = []
            else:
                value["unsupported_points"] = ["仪器型号"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evidence.validate_judgment(value, [REG])

    def test_one_call_timeout_and_original_question_history(self):
        fake = Mock()
        fake.with_options.return_value.chat.completions.create.return_value = response(raw())
        history = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i) * 1500} for i in range(6)]
        with patch.object(evidence, "client", return_value=fake):
            result = evidence.check_evidence("检测顺序与型号？", [REG], query="检测顺序", history=history, cfg=CFG)
        fake.with_options.assert_called_once_with(timeout=20, max_retries=0)
        create = fake.with_options.return_value.chat.completions.create
        create.assert_called_once()
        payload = json.loads(create.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(payload["question"], "检测顺序与型号？")
        self.assertEqual(payload["retrieval_query"], "检测顺序")
        self.assertLessEqual(sum(len(h["content"]) for h in payload["history"]), 4000)
        self.assertLessEqual(len(payload["history"]), 4)
        self.assertEqual(result["judge_calls"], 1)

    def test_failure_and_invalid_response_unverified(self):
        for value in ("not-json", json.dumps({"status": "supported"})):
            fake = Mock()
            fake.with_options.return_value.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])
            with patch.object(evidence, "client", return_value=fake):
                result = evidence.check_evidence("规范要求？", [REG], cfg=CFG)
            self.assertEqual(result["status"], "unverified")
            self.assertEqual(result["accepted_refs"], [])
        with patch.object(evidence, "client", side_effect=TimeoutError):
            self.assertEqual(evidence.check_evidence("规范要求？", [REG], cfg=CFG)["status"], "unverified")

    def test_mock_zero_calls_and_candidate_render(self):
        cfg = SimpleNamespace(mock_mode=True, dashscope_api_key="", rag_evidence_check_enabled=True)
        with patch.object(evidence, "client") as client:
            result = evidence.check_evidence("规范要求？", [REG], cfg=cfg)
        client.assert_not_called()
        self.assertEqual(result["status"], "unverified")
        self.assertIn(REG["content"], evidence.render_evidence(result))
        artifact = evidence.evidence_artifact(result)
        self.assertEqual(artifact["title"], "候选条款")
        self.assertEqual(artifact["data"]["refs"], [])

    def test_overall_deadline_does_not_wait_for_late_response(self):
        release = Event()
        fake = Mock()
        fake.with_options.return_value.chat.completions.create.side_effect = lambda **kw: (release.wait(1), response(raw()))[1]
        try:
            with patch.object(evidence, "client", return_value=fake), patch.object(evidence, "JUDGE_TIMEOUT", 0.01):
                result = evidence.check_evidence("气体检测顺序？", [REG], cfg=CFG)
            self.assertEqual(result["status"], "unverified")
            self.assertEqual(result["accepted_refs"], [])
            self.assertEqual(result["validation_error"], "TimeoutError")
            fake.with_options.return_value.chat.completions.create.assert_called_once()
        finally:
            release.set()

    def test_original_bypass_is_strict(self):
        for question in ("请查第3.9.3条原文", "显示3.9.3和3.2.1正文", "第3.9.3条原文"):
            self.assertTrue(evidence.original_request(question))
        for question in ("解释第3.9.3条", "第3.9.3条说明检测仪必须是什么型号？", "查询第3.9.3条原文并说明型号", "3.9.3", "版本3.9.3.4原文"):
            self.assertFalse(evidence.original_request(question))
        with patch.object(evidence, "client") as client:
            result = evidence.check_evidence("请查第3.9.3条原文", [REG], cfg=CFG)
            missing = evidence.check_evidence("请查第99.99.99条原文", [], cfg=CFG)
        client.assert_not_called()
        self.assertTrue(result["original"])
        self.assertEqual(missing["status"], "insufficient")

    def test_context_budget_whole_clauses_and_no_full_support(self):
        long = dict(REG, content="超长" * 5000, clause_no="第3.9.4条")
        fake = Mock()
        fake.with_options.return_value.chat.completions.create.return_value = response(raw())
        with patch.object(evidence, "client", return_value=fake), self.assertLogs("zhuan.evidence", level="WARNING"):
            result = evidence.check_evidence("全部要求？", [long, REG], cfg=CFG)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["candidates"], [REG])


class IntegrationTest(unittest.TestCase):
    def test_search_unverified_terminal_no_generated_answer(self):
        with patch.object(chat_agent, "evidence_enabled", return_value=True), patch("app.rag.retriever.search", return_value=[REG]), patch.object(chat_agent, "check_evidence", return_value=evidence.unverified("不可用", [REG])):
            out = chat_agent._exec_search(None, None, None, {"query": "气体检测"}, question="型号是什么？")
        self.assertIsInstance(out, chat_agent.Terminal)
        self.assertEqual(out.refs, [])
        self.assertEqual(out.artifact["title"], "候选条款")

    def test_supported_tool_only_passes_accepted_regs(self):
        result = evidence.validate_judgment(raw("partial"), [REG])
        with patch.object(chat_agent, "evidence_enabled", return_value=True), patch("app.rag.retriever.search", return_value=[REG, dict(REG, clause_no="第3.2.1条")]), patch.object(chat_agent, "check_evidence", return_value=result) as judge:
            out, refs = chat_agent._exec_search(None, None, None, {"query": "检测"}, question="检测顺序和型号？", history=[])
        self.assertEqual(out["regulations"], [{"candidate_id": "C1", **evidence.ref_of(REG), "content": REG["content"]}])
        self.assertEqual(out["unsupported_points"], ["仪器型号"])
        self.assertEqual(judge.call_args.args[0], "检测顺序和型号？")

    def test_filtered_payload_preserves_original_candidate_id(self):
        value = raw()
        value["supported_points"][0]["evidence"][0]["candidate_id"] = "C2"
        value["accepted_refs"] = ["C2"]
        result = evidence.validate_judgment(value, [dict(REG, clause_no="第3.9.4条"), REG])
        payload = evidence.answer_payload(result)
        self.assertEqual(len(payload["regulations"]), 1)
        self.assertEqual(payload["regulations"][0]["candidate_id"], "C2")
        self.assertNotIn("score", payload["regulations"][0])

    def test_agent_hides_pretool_claim_and_uses_current_question(self):
        terminal = chat_agent.Terminal("当前知识库未找到足够依据", artifact={"type": "clause_refs", "data": {"refs": [], "status": "insufficient"}})
        slots = {0: {"id": "one", "name": "search_regulations", "arguments": '{"query":"检测"}'}}
        with patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "evidence_enabled", return_value=True), patch.object(chat_agent, "_stream_llm_round", return_value=(["仪器必须ABC型号"], slots, None)), patch.object(chat_agent, "_exec_search", return_value=terminal) as search:
            events = list(chat_agent.run_agent(None, None, None, "型号是什么？", [], tools=[next(t for t in chat_agent.TOOLS if t.name == "search_regulations")], system_prompt="测试"))
        text = "".join(e.get("text", "") for e in events)
        self.assertNotIn("ABC", text)
        self.assertIn("未找到足够依据", text)
        self.assertEqual(search.call_args.kwargs["question"], "型号是什么？")

    def test_no_tool_answer_cannot_bypass_check(self):
        with patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "evidence_enabled", return_value=True), patch.object(chat_agent, "_stream_llm_round", return_value=(["规定100米"], {}, None)), patch.object(chat_agent, "_exec_search", return_value=chat_agent.Terminal("依据不足", refs=[])) as search:
            with self.assertRaises(RuntimeError):
                list(chat_agent.run_agent(None, None, None, "标准是多少？", [], tools=[next(t for t in chat_agent.TOOLS if t.name == "search_regulations")], system_prompt="测试"))
        search.assert_not_called()

    def test_unverified_clears_previous_confirmed_refs(self):
        slots = {0: {"id": "one", "name": "search_regulations", "arguments": '{"query":"检测"}'}}
        confirmed = evidence.ref_of(REG)
        terminal = chat_agent.Terminal("未经依据核验，仅供查阅", refs=[], artifact=evidence.evidence_artifact(evidence.unverified("失败", [REG])))
        with patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "evidence_enabled", return_value=True), patch.object(chat_agent, "_stream_llm_round", return_value=([], slots, None)), patch.object(chat_agent, "_exec_search", side_effect=[({"status": "supported"}, [confirmed]), terminal]), patch.object(chat_agent, "_artifact_for_tool", return_value=None):
            events = list(chat_agent.run_agent(None, None, None, "检测要求？", [], tools=[next(t for t in chat_agent.TOOLS if t.name == "search_regulations")], system_prompt="测试"))
        self.assertEqual(next(e["refs"] for e in events if e["type"] == "refs"), [])

    def test_report_generation_failure_keeps_only_verified_requirements(self):
        result = evidence.validate_judgment(raw("partial"), [REG])
        with patch.object(assessor, "chat_text", return_value=None) as chat:
            suggestion = assessor.build_suggestion({"hazard_type": "其他-待归类"}, [REG], evidence=result)
        self.assertIn("只使用下方已支持要点", chat.call_args.args[0])
        self.assertIn("已核验依据", suggestion)
        self.assertIn("先检测氧气", suggestion)
        self.assertIn("仪器型号", suggestion)

    def test_rule_fallback_uses_same_artifact(self):
        user, project = SimpleNamespace(name="测试", role="safety_officer"), SimpleNamespace(name="测试", id=1)
        artifact = evidence.evidence_artifact(evidence.unverified("失败", [REG]))
        with patch("app.routers.chat.kb_response", return_value=("候选原文", [], artifact)):
            events = list(_rule_fallback(None, user, project, "规范依据", history=[]))
        self.assertEqual(next(e["artifact"] for e in events if e["type"] == "artifact"), artifact)

    def test_all_report_states_do_not_change_risk_or_dispatch(self):
        ext = {"building": "3号楼", "floor": "12层", "hazard_type": "高处作业-洞口防护", "risk_level": "高"}
        for status in ("supported", "partial", "insufficient", "unverified"):
            result = evidence.validate_judgment(raw("partial" if status == "partial" else "supported"), [REG]) if status in ("supported", "partial") else evidence.unverified("测试", [REG])
            result["status"] = status
            with patch.object(graph, "evidence_enabled", return_value=True), patch.object(graph, "extract_hazard", return_value=ext), patch.object(graph, "kb_search", return_value=[REG]), patch.object(graph, "check_evidence", return_value=result), patch.object(graph, "match_responsible", return_value={"primary_user_id": 7}), patch.object(assessor, "chat_text", return_value="【立即措施】停止作业") as chat:
                draft = graph.process_report(None, "3号楼12层井口无防护", "text")["order_draft"]
            self.assertEqual(draft["risk_level"], "高")
            self.assertEqual(draft["responsible_user_id"], 7)
            if status in ("insufficient", "unverified"):
                chat.assert_not_called()
                self.assertEqual(draft["regulation_refs"], [])
                self.assertIn("规范依据待人工核实", draft["suggestion"])
            elif status == "partial":
                self.assertIn("仪器型号", draft["suggestion"])


class CorpusTest(unittest.TestCase):
    def test_fixed_split_and_no_family_leak(self):
        from collections import Counter
        qa = cases()
        self.assertEqual(len(qa), 80)
        self.assertEqual(len({c["id"] for c in qa}), 80)
        for split in ("development", "acceptance"):
            self.assertEqual(Counter(c["category"] for c in qa if c["split"] == split), {"supported": 10, "partial": 10, "unrelated": 10, "missing": 10})
        self.assertFalse({c["family_id"] for c in qa if c["split"] == "development"} & {c["family_id"] for c in qa if c["split"] == "acceptance"})
        self.assertEqual(Counter(c["expected"] for c in REPORT_CASES), {"supported": 3, "partial": 3, "insufficient": 3, "unverified": 3})


class EvaluationGateTest(unittest.TestCase):
    def test_gate_requires_semantics_real_modes_and_valid_evidence(self):
        from copy import deepcopy
        from scripts.evaluate_relevance import apply_review
        records, qa = [], {}
        for case in [c for c in cases() if c["split"] == "acceptance"]:
            result = evidence.validate_judgment(raw("partial" if case["expected"] == "partial" else "supported"), [REG])
            if case["expected"] == "insufficient":
                result.update(status="insufficient", supported_points=[], accepted_refs=[])
            records.append({**case, "retrieval_mode": "vector", "candidates": [REG], "baseline": {"answer": "测试"},
                            "optimized": {"evidence": result, "judge_ms": 1, "state_correct": True, "required_refs_covered": True}, "semantic_review": None})
            qa[case["id"]] = {"supported_points_valid": True, "unsupported_points_complete": True, "answer_grounded": True, "baseline_unsupported_claim": False, "notes": "测试复核"}
        report = {"cases_sha256": "cases", "judge_prompt_sha256": "prompt", "records": records, "remote": True, "mode": "vector",
                  "reports": [{"id": c["id"], "behavior_passed": True, "retrieval_mode": "vector"} for c in REPORT_CASES]}
        review = {"cases_sha256": "cases", "judge_prompt_sha256": "prompt", "qa": qa,
                  "reports": {c["id"]: {"grounded": True, "notes": "测试复核"} for c in REPORT_CASES}}
        self.assertTrue(apply_review(deepcopy(report), deepcopy(review))["enable_gate_passed"])
        for failure in ("semantic", "mode", "quote"):
            candidate, reviewed = deepcopy(report), deepcopy(review)
            if failure == "semantic":
                reviewed["qa"]["P11"]["unsupported_points_complete"] = False
                reviewed["qa"]["P12"]["unsupported_points_complete"] = False
            elif failure == "mode":
                candidate["reports"][0]["retrieval_mode"] = "keyword"
            else:
                candidate["records"][0]["optimized"]["evidence"]["supported_points"][0]["evidence"][0]["quote"] = "正文不存在的虚构要求"
            with self.subTest(failure=failure):
                self.assertFalse(apply_review(candidate, reviewed)["enable_gate_passed"])


if __name__ == "__main__":
    unittest.main()
