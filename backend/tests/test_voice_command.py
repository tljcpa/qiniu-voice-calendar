"""语音指令编排端到端测试。

注入假 LLM（返回固定意图）+ 真实内存库 + 真实 time_parser，
覆盖 add/view/delete/update/clarify/unknown 各分支，全脱网（遵 D-12）。
"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import handle_command

NOW = datetime(2026, 5, 29, 10, 0)  # 周五


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
    """假 LLM：complete_json 恒返回预设意图 dict。"""

    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, **kwargs):
        return self.payload


def test_add_success(session):
    llm = FakeLLM({"intent": "add", "title": "产品评审会", "time_expr": "明天下午三点"})
    r = handle_command("明天下午三点开产品评审会", session=session, now=NOW, llm=llm)
    assert r["intent"] == "add"
    assert r["ok"] is True
    assert "产品评审会" in r["speech"]
    assert len(r["events"]) == 1
    assert r["events"][0]["start_at"] == "2026-05-30T15:00:00"


def test_add_missing_time_clarifies(session):
    llm = FakeLLM({"intent": "add", "title": "会", "time_expr": None})
    r = handle_command("帮我加个会", session=session, now=NOW, llm=llm)
    assert r["ok"] is False
    assert r["needs_clarification"] is True


def test_add_conflict_not_created_with_suggestion(session):
    # 先占 15:00-16:00
    crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({"intent": "add", "title": "新会", "time_expr": "明天下午三点"})
    r = handle_command("明天下午三点开新会", session=session, now=NOW, llm=llm)
    assert r["ok"] is False
    assert r["needs_clarification"] is True
    assert "冲突" in r["speech"]
    # 未创建
    assert crud.find_events(session, keyword="新会") == []


def test_add_conflict_force_creates(session):
    crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({"intent": "add", "title": "新会", "time_expr": "明天下午三点"})
    r = handle_command("明天下午三点开新会", session=session, now=NOW, llm=llm, force=True)
    assert r["ok"] is True
    assert len(crud.find_events(session, keyword="新会")) == 1


def test_add_recurring_creates_multiple(session):
    llm = FakeLLM({"intent": "add", "title": "晨会", "time_expr": "每周一三五早上九点"})
    r = handle_command("每周一三五早上九点晨会", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    assert len(r["events"]) >= 3
    assert "个" in r["speech"]


def test_view_empty(session):
    llm = FakeLLM({"intent": "view", "time_expr": "今天"})
    r = handle_command("今天有什么安排", session=session, now=NOW, llm=llm)
    assert r["intent"] == "view"
    assert "没有安排" in r["speech"]


def test_view_lists_events(session):
    crud.create_event(session, title="评审", start_at=datetime(2026, 5, 29, 10, 0))
    crud.create_event(session, title="对接", start_at=datetime(2026, 5, 29, 14, 0))
    llm = FakeLLM({"intent": "view", "time_expr": "今天"})
    r = handle_command("今天有什么安排", session=session, now=NOW, llm=llm)
    assert "2" in r["speech"]
    assert "评审" in r["speech"] and "对接" in r["speech"]


def test_delete_single(session):
    crud.create_event(session, title="羽毛球", start_at=datetime(2026, 5, 30, 19, 0))
    llm = FakeLLM({"intent": "delete", "target_query": "羽毛球"})
    r = handle_command("把羽毛球删了", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    assert "已删除" in r["speech"]
    assert crud.find_events(session, keyword="羽毛球") == []


def test_delete_ambiguous_clarifies(session):
    crud.create_event(session, title="项目评审会", start_at=datetime(2026, 5, 30, 10, 0))
    crud.create_event(session, title="客户对接会", start_at=datetime(2026, 5, 30, 14, 0))
    llm = FakeLLM({"intent": "delete", "target_query": "会"})
    r = handle_command("把那个会删了", session=session, now=NOW, llm=llm)
    assert r["ok"] is False
    assert r["needs_clarification"] is True
    assert len(r["candidates"]) == 2


def test_delete_not_found(session):
    llm = FakeLLM({"intent": "delete", "target_query": "聚餐"})
    r = handle_command("把聚餐删了", session=session, now=NOW, llm=llm)
    assert r["ok"] is False
    assert "没有找到" in r["speech"]


def test_update_shift(session):
    crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({
        "intent": "update",
        "target_query": "客户对接",
        "new_values": {"shift": "往后一小时"},
    })
    r = handle_command("把客户对接往后挪一小时", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    assert r["events"][0]["start_at"] == "2026-05-30T16:00:00"


def test_update_to_specific_time(session):
    crud.create_event(session, title="会", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({
        "intent": "update",
        "target_query": "会",
        "new_values": {"time_expr": "明天下午四点"},
    })
    r = handle_command("把会改到明天下午四点", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    assert r["events"][0]["start_at"] == "2026-05-30T16:00:00"


def test_clarify_passthrough(session):
    llm = FakeLLM({"intent": "clarify", "clarification": "你指哪个会？"})
    r = handle_command("改一下我的会", session=session, now=NOW, llm=llm)
    assert r["intent"] == "clarify"
    assert r["speech"] == "你指哪个会？"


def test_unknown(session):
    llm = FakeLLM({"intent": "unknown"})
    r = handle_command("今天天气怎么样", session=session, now=NOW, llm=llm)
    assert r["intent"] == "unknown"
    assert r["ok"] is False
