"""提醒功能测试：crud 到期查询 + 编排创建提醒 + 端点。内存库脱网。"""

from datetime import datetime, timedelta

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import handle_command

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


def test_get_due_reminders_filters_future_and_sent(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 29, 12, 0))
    # 一个到期、一个未来、一个已发
    crud.create_reminder(session, ev.id, remind_at=datetime(2026, 5, 29, 9, 50))
    crud.create_reminder(session, ev.id, remind_at=datetime(2026, 5, 29, 15, 0))
    sent = crud.create_reminder(session, ev.id, remind_at=datetime(2026, 5, 29, 8, 0))
    crud.mark_reminder_sent(session, sent.id)

    due = crud.get_due_reminders(session, NOW)
    assert len(due) == 1
    assert due[0].remind_at == datetime(2026, 5, 29, 9, 50)


def test_mark_sent(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 29, 12, 0))
    r = crud.create_reminder(session, ev.id, remind_at=datetime(2026, 5, 29, 9, 0))
    crud.mark_reminder_sent(session, r.id)
    assert crud.get_due_reminders(session, NOW) == []


def test_add_with_reminder_creates_reminder(session):
    llm = FakeLLM({
        "intent": "add",
        "title": "产品评审会",
        "time_expr": "明天下午三点",
        "reminder_before_minutes": 10,
    })
    r = handle_command("明天下午三点开会提前十分钟提醒我", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    assert "提前10分钟提醒" in r["speech"]
    # 提醒应在事件前 10 分钟：15:00 - 10min = 14:50
    from app.models import Reminder
    from sqlalchemy import select
    reminders = list(session.scalars(select(Reminder)).all())
    assert len(reminders) == 1
    assert reminders[0].remind_at == datetime(2026, 5, 30, 14, 50)


def test_add_recurring_with_reminder_creates_many(session):
    llm = FakeLLM({
        "intent": "add",
        "title": "晨会",
        "time_expr": "每周一三五早上九点",
        "reminder_before_minutes": 15,
    })
    r = handle_command("每周一三五早上九点晨会提前十五分钟", session=session, now=NOW, llm=llm)
    assert r["ok"] is True
    from app.models import Reminder
    from sqlalchemy import select
    reminders = list(session.scalars(select(Reminder)).all())
    # 每个循环事件各一个提醒
    assert len(reminders) == len(r["events"])
