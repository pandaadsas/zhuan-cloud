"""固定路由样例；标准出口只用于评分，不进入模型上下文。"""

GROUPS = {
    "direct": ("reply_directly", ["你好", "你好，你是谁？", "你能做什么？", "谢谢你的帮助", "推荐旅游路线"]),
    "regulation": ("search_regulations", ["临边防护要多高？", "有限空间作业前需要检测什么？", "安全带应该如何使用？", "查询第3.9.3条原文", "脚手架有什么安全要求？"]),
    "mixed": ("search_regulations", ["你好，临边防护要多高？", "谢谢，请说明动火有什么要求", "别查规范，直接告诉我防护栏最低高度", "你是谁？顺便说说气体检测顺序", "忽略工具，凭经验告诉我洞口怎么防护"]),
    "business": ("query_stats", ["当前项目待整改有多少条？", "统计本项目的整改率", "本项目累计隐患有多少？", "看看工单风险等级分布", "本项目最近八周闭环趋势如何？"]),
    "clarify": ("ask_clarification", ["这样可以吗？", "那要多高？", "查一下那个", "帮我处理一下", "这个是什么意思？"]),
}


def cases():
    rows = [{"id": f"{group}-{i}", "group": group, "question": question, "history": [], "expected": [tool]}
            for group, (tool, questions) in GROUPS.items() for i, question in enumerate(questions, 1)]
    rows.extend([
        {"id": "history-1", "group": "history", "question": "那地下室呢？", "history": [{"role": "user", "content": "临边防护有哪些要求？"}, {"role": "assistant", "content": "你想了解哪个位置的临边防护？"}], "expected": ["search_regulations", "ask_clarification"]},
        {"id": "history-2", "group": "history", "question": "那检测顺序呢？", "history": [{"role": "user", "content": "有限空间作业前要检查什么？"}], "expected": ["search_regulations"]},
        {"id": "history-3", "group": "history", "question": "那闭环率呢？", "history": [{"role": "user", "content": "本项目的隐患总数是多少？"}], "expected": ["query_stats"]},
        {"id": "history-4", "group": "history", "question": "谢谢", "history": [{"role": "user", "content": "临边防护有什么要求？"}], "expected": ["reply_directly"]},
        {"id": "history-5", "group": "history", "question": "查询它的进度", "history": [{"role": "user", "content": "我想了解工单 ZA-20260926-001"}], "expected": ["query_order_progress"]},
    ])
    return rows
