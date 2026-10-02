import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.agents import chat_agent, chat_tools
from app.routers.chat import _rule_fallback


CFG = SimpleNamespace(rag_evidence_check_enabled=True)
USER = SimpleNamespace(name="测试", role="safety_officer")
PROJECT = SimpleNamespace(id=1, name="测试项目")


def slot(name, args):
    return {"id": "test", "name": name, "arguments": json.dumps(args, ensure_ascii=False)}


class RoutingTest(unittest.TestCase):
    def test_routing_prompt_only_for_safety_profile(self):
        with patch.object(chat_agent, "get_cfg", return_value=CFG):
            self.assertIn("reply_directly", chat_agent._system_prompt(USER, PROJECT))
            self.assertNotIn("reply_directly", chat_agent._pm_system_prompt(USER, PROJECT))

    def test_model_selected_conversation_one_call_no_retrieval(self):
        for name in chat_agent.CONVERSATION_TOOLS:
            with self.subTest(name=name), patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "_stream_llm_round", return_value=(["不应显示"], {0: slot(name, {"text": "你好，请问需要什么帮助？"})}, None)) as model, patch.object(chat_agent, "_exec_search") as search:
                history = [{"role": "user", "content": "之前的问题"}]
                events = list(chat_agent.run_agent(None, USER, PROJECT, "你好", history))
            model.assert_called_once()
            search.assert_not_called()
            self.assertIn(history[0], model.call_args.args[1])
            self.assertFalse(any(e["type"] in ("artifact", "tool") for e in events))
            self.assertEqual(next(e["refs"] for e in events if e["type"] == "refs"), [])
            self.assertNotIn("不应显示", "".join(e.get("text", "") for e in events))

    def test_invalid_route_fails_before_output_or_execution(self):
        invalid = [{}, {0: slot("unknown", {})}, {0: slot("reply_directly", {})},
                   {0: slot("reply_directly", {"text": 1})}, {0: slot("reply_directly", {"text": " "})},
                   {0: slot("reply_directly", {"text": "你好", "refs": []})},
                   {0: slot("reply_directly", {"text": "你好"}), 1: slot("query_stats", {})},
                   {0: slot("search_regulations", {"query": ""})},
                   {0: slot("query_stats", [])}, {0: {"id": "x", "name": "query_stats", "arguments": "{"}}]
        for slots in invalid:
            with self.subTest(slots=slots), patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "_stream_llm_round", return_value=(["未经核验"], slots, None)), patch.object(chat_agent, "_exec_search") as search:
                with self.assertRaises(RuntimeError):
                    next(chat_agent.run_agent(None, USER, PROJECT, "测试", []))
                search.assert_not_called()

    def test_business_tool_can_finish_without_rag(self):
        tool = next(t for t in chat_agent.TOOLS if t.name == "query_stats")
        rounds = [([], {0: slot("query_stats", {})}, None), (["当前没有工单"], {}, None)]
        with patch.object(chat_agent, "get_cfg", return_value=CFG), patch.object(chat_agent, "_stream_llm_round", side_effect=rounds), patch.object(tool, "executor", return_value=({"total": 0}, [])) as execute, patch.object(chat_agent, "_exec_search") as search:
            events = list(chat_agent.run_agent(None, USER, PROJECT, "多少工单", []))
        execute.assert_called_once()
        search.assert_not_called()
        self.assertEqual(events[-1]["type"], "done")

    def test_fallback_no_default_kb_and_no_greeting_substring_bypass(self):
        for msg in ("你好", "你好，你是谁？", "推荐旅游路线", "这样可以吗？", "那要多少米？"):
            with self.subTest(msg=msg), patch("app.routers.chat.kb_response") as search:
                events = list(_rule_fallback(None, USER, PROJECT, msg))
            search.assert_not_called()
            self.assertFalse(any(e["type"] == "artifact" for e in events))
        for msg in ("你好，临边防护要多高？", "防护栏高度是多少？", "查询第3.9.3条"):
            self.assertIsNone(chat_tools.fallback_conversation(msg))
            self.assertEqual(chat_tools.classify(msg), "kb")
        self.assertEqual(chat_tools.classify("待整改有多少条？"), "stats")


if __name__ == "__main__":
    unittest.main()
