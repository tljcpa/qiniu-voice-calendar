"""多轮澄清指代消解测试。内存库 + 真实选择逻辑，脱网。"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import handle_resolve, resolve_selection

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


def _cands():
    return [
        {"id": 1, "title": "项目评审会", "start_at": "2026-05-30T10:00:00"},
        {"id": 2, "title": "客户对接", "start_at": "2026-05-30T15:00:00"},
        {"id": 3, "title": "部门聚餐", "start_at": "2026-05-30T19:00:00"},
    ]


def test_select_ordinal():
    assert resolve_selection("第一个", _cands()) == 0
    assert resolve_selection("第二个", _cands()) == 1
    assert resolve_selection("最后那个", _cands()) == 2


def test_select_by_period():
    # 上午只有项目评审会(10点)
    assert resolve_selection("上午那个", _cands()) == 0
    # 下午只有客户对接(15点)
    assert resolve_selection("下午那个", _cands()) == 1
    # 晚上只有部门聚餐(19点)
    assert resolve_selection("晚上那个", _cands()) == 2


def test_select_by_title_keyword():
    assert resolve_selection("把客户对接那个", _cands()) == 1
    assert resolve_selection("聚餐", _cands()) == 2


def test_select_ambiguous_returns_none():
    # 没有可区分信息
    assert resolve_selection("那个吧", _cands()) is None


def test_resolve_delete_executes(session):
    e1 = crud.create_event(session, title="项目评审会", start_at=datetime(2026, 5, 30, 10, 0))
    e2 = crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    candidates = [e1.to_dict(), e2.to_dict()]
    r = handle_resolve("下午那个", intent="delete", candidates=candidates, session=session, now=NOW)
    assert r["ok"] is True
    assert "客户对接" in r["speech"]
    # 只删了客户对接
    assert crud.get_event(session, e2.id) is None
    assert crud.get_event(session, e1.id) is not None


def test_resolve_update_executes(session):
    e1 = crud.create_event(session, title="项目评审会", start_at=datetime(2026, 5, 30, 10, 0))
    e2 = crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 30, 15, 0))
    candidates = [e1.to_dict(), e2.to_dict()]
    r = handle_resolve(
        "第一个", intent="update", candidates=candidates, session=session, now=NOW,
        new_values={"shift": "往后一小时"},
    )
    assert r["ok"] is True
    # 项目评审会 10:00 -> 11:00
    assert r["events"][0]["start_at"] == "2026-05-30T11:00:00"


def test_resolve_unresolvable_reasks(session):
    e1 = crud.create_event(session, title="会A", start_at=datetime(2026, 5, 30, 15, 0))
    e2 = crud.create_event(session, title="会B", start_at=datetime(2026, 5, 30, 15, 30))
    candidates = [e1.to_dict(), e2.to_dict()]
    # 都在下午，时段无法区分，且无序数/标题 → 再问
    r = handle_resolve("那个", intent="delete", candidates=candidates, session=session, now=NOW)
    assert r["ok"] is False
    assert r["needs_clarification"] is True
