"""纯指代删除断链修复测试（必修）。

复现 E2E bug：把那个会删了 → 问哪个 → 第一个 → 必须真删除，不死循环。
LLM 对纯指代返回 intent=clarify；修复后 clarify 分支查库列候选 + resolve_intent，
前端据此建 pending，下一句指代消解执行。
"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import (
    _infer_clarify_action,
    _strip_demonstratives,
    handle_command,
    handle_resolve,
)

NOW = datetime(2026, 5, 29, 10, 0)


@pytest.fixture()
def session():
    engine = make_engine("sqlite://")
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    s = make_session_factory(engine)()
    try:
        yield s
    finally:
        s.close()


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, **kwargs):
        return self.payload


# 模拟 LLM 对"把那个会删了"的真实返回
CLARIFY_DELETE = {
    "intent": "clarify",
    "target_query": "那个会",
    "clarification": "你指的是哪个日程？",
}


def test_strip_demonstratives():
    assert _strip_demonstratives("那个会") == "会"
    assert _strip_demonstratives("刚才那个评审会") == "评审会"
    assert _strip_demonstratives("那个") == ""
    assert _strip_demonstratives(None) == ""


def test_infer_action():
    assert _infer_clarify_action("把那个会删了") == "delete"
    assert _infer_clarify_action("把那个会往后挪一小时") == "update"
    assert _infer_clarify_action("加个会") is None


def test_pure_reference_delete_full_loop(session):
    """核心：把那个会删了 → 列候选(clarify) → 第一个 → 真删除，不死循环。"""
    crud.create_event(session, title="项目评审会", start_at=datetime(2026, 5, 30, 10, 0))
    crud.create_event(session, title="客户对接会", start_at=datetime(2026, 5, 30, 15, 0))

    # 第一步：纯指代 → clarify 列候选 + resolve_intent=delete
    r1 = handle_command("把那个会删了", session=session, now=NOW, llm=FakeLLM(CLARIFY_DELETE))
    assert r1["intent"] == "clarify"
    assert r1["needs_clarification"] is True
    assert len(r1["candidates"]) == 2
    assert r1["resolve_intent"] == "delete"

    # 第二步：用户"第一个" → 指代消解 → 真删除项目评审会
    r2 = handle_resolve(
        "第一个", intent=r1["resolve_intent"], candidates=r1["candidates"], session=session, now=NOW
    )
    assert r2["ok"] is True
    assert "已删除" in r2["speech"]
    assert crud.find_events(session, keyword="项目评审会") == []
    # 客户对接会仍在
    assert len(crud.find_events(session, keyword="客户对接会")) == 1


def test_pure_reference_delete_unique_executes_directly(session):
    """纯指代但库中唯一匹配 → 直接删除，不再追问。"""
    crud.create_event(session, title="周会", start_at=datetime(2026, 5, 30, 10, 0))
    r = handle_command("把那个会删了", session=session, now=NOW, llm=FakeLLM(CLARIFY_DELETE))
    assert r["intent"] == "delete"
    assert r["ok"] is True
    assert crud.find_events(session, keyword="周会") == []


def test_pure_reference_delete_no_match(session):
    r = handle_command("把那个会删了", session=session, now=NOW, llm=FakeLLM(CLARIFY_DELETE))
    assert r["ok"] is False
    assert "没有找到" in r["speech"]


def test_clarify_without_action_keeps_question(session):
    """缺时间的添加类 clarify（无删/改动作）→ 原样追问，不列候选。"""
    payload = {"intent": "clarify", "title": "会", "clarification": "这个会安排在什么时间？", "missing": ["time"]}
    r = handle_command("帮我加个会", session=session, now=NOW, llm=FakeLLM(payload))
    assert r["intent"] == "clarify"
    assert r["needs_clarification"] is True
    assert r["candidates"] == []
    assert "时间" in r["speech"]
