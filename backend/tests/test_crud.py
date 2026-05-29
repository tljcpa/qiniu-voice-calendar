"""日历 CRUD 单元测试。

用内存 SQLite（StaticPool），每个测试独立建表，不触碰真实库、不触网（遵 D-12）。
"""

from datetime import datetime, timedelta

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud


@pytest.fixture()
def session():
    """每个测试一个全新的内存库会话。"""
    engine = make_engine("sqlite://")
    # 触发模型注册后建表
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    s = factory()
    try:
        yield s
    finally:
        s.close()


def test_create_event_defaults_end_at(session):
    """不传 end_at 时默认 +1 小时。"""
    start = datetime(2026, 5, 30, 15, 0)
    ev = crud.create_event(session, title="产品评审会", start_at=start)
    assert ev.id is not None
    assert ev.end_at == start + timedelta(hours=1)
    assert ev.attendees == []


def test_create_with_attendees_and_location(session):
    ev = crud.create_event(
        session,
        title="客户对接",
        start_at=datetime(2026, 5, 30, 16, 0),
        location="会议室A",
        attendees=["小王", "小李"],
    )
    fetched = crud.get_event(session, ev.id)
    assert fetched.location == "会议室A"
    assert fetched.attendees == ["小王", "小李"]


def test_list_events_by_range_ordered(session):
    crud.create_event(session, title="晚", start_at=datetime(2026, 5, 30, 18, 0))
    crud.create_event(session, title="早", start_at=datetime(2026, 5, 30, 9, 0))
    crud.create_event(session, title="次日", start_at=datetime(2026, 5, 31, 9, 0))

    day = crud.list_events(
        session,
        start=datetime(2026, 5, 30, 0, 0),
        end=datetime(2026, 5, 30, 23, 59),
    )
    titles = [e.title for e in day]
    assert titles == ["早", "晚"]  # 升序 + 范围过滤掉次日


def test_find_events_by_keyword(session):
    crud.create_event(session, title="项目评审会", start_at=datetime(2026, 5, 30, 10, 0))
    crud.create_event(session, title="客户对接会", start_at=datetime(2026, 5, 30, 14, 0))
    crud.create_event(session, title="羽毛球", start_at=datetime(2026, 5, 30, 19, 0))

    hits = crud.find_events(session, keyword="会")
    assert len(hits) == 2  # 两个含"会"，歧义澄清场景


def test_update_event(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 30, 15, 0))
    updated = crud.update_event(
        session, ev.id, start_at=datetime(2026, 5, 30, 16, 0), location="新地点"
    )
    assert updated.start_at == datetime(2026, 5, 30, 16, 0)
    assert updated.location == "新地点"


def test_update_ignores_unknown_field(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 30, 15, 0))
    updated = crud.update_event(session, ev.id, nonexistent="x", title="改名")
    assert updated.title == "改名"
    assert not hasattr(updated, "nonexistent")


def test_update_missing_returns_none(session):
    assert crud.update_event(session, 999, title="x") is None


def test_delete_event(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 30, 15, 0))
    assert crud.delete_event(session, ev.id) is True
    assert crud.get_event(session, ev.id) is None


def test_delete_missing_returns_false(session):
    assert crud.delete_event(session, 999) is False


def test_event_to_dict(session):
    ev = crud.create_event(
        session, title="会", start_at=datetime(2026, 5, 30, 15, 0),
        attendees=["小王"],
    )
    d = ev.to_dict()
    assert d["title"] == "会"
    assert d["start_at"] == "2026-05-30T15:00:00"
    assert d["attendees"] == ["小王"]


def test_create_reminder_cascade_delete(session):
    ev = crud.create_event(session, title="会", start_at=datetime(2026, 5, 30, 15, 0))
    crud.create_reminder(session, ev.id, remind_at=datetime(2026, 5, 30, 14, 50))
    # 删除事件应级联删除提醒
    crud.delete_event(session, ev.id)
    from app.models import Reminder
    from sqlalchemy import select
    remaining = list(session.scalars(select(Reminder)).all())
    assert remaining == []
