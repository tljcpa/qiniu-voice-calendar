"""冲突确认（接受建议 / 坚持原时间）测试。内存库脱网。"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import handle_command, handle_confirm

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


def _trigger_conflict(session):
    """先占 15:00，再加同点事件触发冲突，返回 pending_conflict。"""
    crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({"intent": "add", "title": "新会", "time_expr": "明天下午三点"})
    r = handle_command("明天下午三点开新会", session=session, now=NOW, llm=llm)
    assert r["ok"] is False
    assert r["pending_conflict"] is not None
    return r["pending_conflict"]


def test_accept_suggestion_creates_at_suggested(session):
    pc = _trigger_conflict(session)
    assert pc["suggested_start"] is not None
    r = handle_confirm(pc, accept_suggestion=True, session=session)
    assert r["ok"] is True
    assert "改到" in r["speech"]
    # 新会创建在建议时间（不是原 15:00）
    new = crud.find_events(session, keyword="新会")
    assert len(new) == 1
    assert new[0].start_at == datetime.fromisoformat(pc["suggested_start"])


def test_insist_creates_at_original(session):
    pc = _trigger_conflict(session)
    r = handle_confirm(pc, accept_suggestion=False, session=session)
    assert r["ok"] is True
    new = crud.find_events(session, keyword="新会")
    assert len(new) == 1
    # 坚持原时间 15:00（明知冲突）
    assert new[0].start_at == datetime(2026, 5, 30, 15, 0)


def test_confirm_carries_attendees_and_reminder(session):
    crud.create_event(session, title="占位", start_at=datetime(2026, 5, 30, 15, 0))
    llm = FakeLLM({
        "intent": "add", "title": "评审", "time_expr": "明天下午三点",
        "attendees": ["小王"], "reminder_before_minutes": 10,
    })
    r = handle_command("明天下午三点评审叫上小王提前十分钟", session=session, now=NOW, llm=llm)
    pc = r["pending_conflict"]
    assert pc["attendees"] == ["小王"]
    assert pc["reminder_min"] == 10
    r2 = handle_confirm(pc, accept_suggestion=True, session=session)
    assert r2["ok"] is True
    ev = crud.find_events(session, keyword="评审")[0]
    assert ev.attendees == ["小王"]
    # 提醒也挂上了
    from app.models import Reminder
    from sqlalchemy import select
    assert len(list(session.scalars(select(Reminder)).all())) == 1
