"""意图解析单元测试。

注入假 LLM（返回固定 JSON），只测解析/校验/默认值逻辑，不触网（遵 D-12）。
真实 prompt 效果用 scripts/tune_intent.py 跑多条话术人工调试。
"""

from app.intent_parser import _normalize, parse_intent


class _FakeLLM:
    """假 LLM：complete_json 直接返回预设 dict，并记录收到的 messages。"""

    def __init__(self, payload):
        self.payload = payload
        self.last_messages = None

    def complete_json(self, messages, **kwargs):
        self.last_messages = messages
        return self.payload


def test_parse_add_intent():
    payload = {
        "intent": "add",
        "confidence": 0.95,
        "title": "产品评审会",
        "time_expr": "明天下午三点",
        "attendees": ["小王"],
    }
    out = parse_intent("明天下午三点开产品评审会叫上小王", llm=_FakeLLM(payload))
    assert out["intent"] == "add"
    assert out["title"] == "产品评审会"
    assert out["time_expr"] == "明天下午三点"
    assert out["attendees"] == ["小王"]
    # 未提供的槽位应有安全默认
    assert out["location"] is None
    assert out["reminder_before_minutes"] is None
    assert out["missing"] == []


def test_unknown_intent_coerced():
    """LLM 返回非法 intent 应归一为 unknown。"""
    out = parse_intent("乱七八糟", llm=_FakeLLM({"intent": "飞天遁地"}))
    assert out["intent"] == "unknown"


def test_clarify_carries_question_and_missing():
    payload = {
        "intent": "clarify",
        "confidence": 0.6,
        "target_query": "那个会",
        "clarification": "你有多个会，想删除哪一个？",
        "missing": ["target"],
    }
    out = parse_intent("把那个会删了", llm=_FakeLLM(payload))
    assert out["intent"] == "clarify"
    assert out["clarification"]
    assert out["missing"] == ["target"]


def test_now_iso_injected_into_prompt():
    """提供 now_iso 时应拼进 user 消息，给 LLM 相对时间上下文。"""
    fake = _FakeLLM({"intent": "view", "time_expr": "今天"})
    parse_intent("今天有啥安排", now_iso="2026-05-30T09:00:00", llm=fake)
    user_msg = fake.last_messages[-1]["content"]
    assert "2026-05-30T09:00:00" in user_msg


def test_normalize_bad_types():
    """各字段类型异常时不应抛错，落到安全默认。"""
    raw = {
        "intent": "add",
        "confidence": "高",          # 非数值
        "attendees": "小王",          # 非列表
        "reminder_before_minutes": "十分钟",  # 非整数
        "missing": None,             # 非列表
        "new_values": "啥",          # 非 dict
    }
    out = _normalize(raw)
    assert out["confidence"] == 0.0
    assert out["attendees"] == []
    assert out["reminder_before_minutes"] is None
    assert out["missing"] == []
    assert out["new_values"] is None
