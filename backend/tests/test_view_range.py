"""查询范围（单日/周/月）测试。内存库 + 假 LLM，脱网。参考日 2026-05-29 周五。"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import _view_range, handle_command

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
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, **kwargs):
        return self.payload


def test_range_today():
    s, e, label, multi = _view_range("今天", NOW)
    assert label == "今天" and multi is False
    assert s.date() == NOW.date()


def test_range_this_week():
    s, e, label, multi = _view_range("这周", NOW)
    assert label == "本周" and multi is True
    # 本周一 = 2026-05-25，周日 = 2026-05-31
    assert s.date() == datetime(2026, 5, 25).date()
    assert e.date() == datetime(2026, 5, 31).date()


def test_range_next_week():
    s, e, label, multi = _view_range("下周", NOW)
    assert label == "下周"
    assert s.date() == datetime(2026, 6, 1).date()


def test_range_this_month():
    s, e, label, multi = _view_range("这个月", NOW)
    assert multi is True
    assert s.date() == datetime(2026, 5, 1).date()
    assert e.date() == datetime(2026, 5, 31).date()


def test_range_last_month():
    s, e, label, multi = _view_range("上个月", NOW)
    assert label == "上个月" and multi is True
    assert s.date() == datetime(2026, 4, 1).date()
    assert e.date() == datetime(2026, 4, 30).date()


def test_specific_month_name_not_current_month():
    # "六月有什么安排" 应是 6 月范围，绝不能误判成当前 5 月
    s, e, label, multi = _view_range("六月有什么安排", NOW)
    assert label == "6月" and multi is True
    assert s.date() == datetime(2026, 6, 1).date()
    assert e.date() == datetime(2026, 6, 30).date()


def test_specific_month_arabic():
    s, e, label, multi = _view_range("7月", NOW)
    assert s.date() == datetime(2026, 7, 1).date()


def test_month_day_is_single_day_not_range():
    # "六月十八号" 带具体日 → 不是月范围（交给单日逻辑）
    _, _, _, multi = _view_range("六月十八号", NOW)
    assert multi is False


def test_specific_weekday_still_single_day():
    # "下周三" 带具体星期几 → 单日，不是周范围
    s, e, label, multi = _view_range("下周三", NOW)
    assert multi is False


def test_view_this_week_lists_across_days(session):
    crud.create_event(session, title="产品评审", start_at=datetime(2026, 5, 29, 15, 0))
    crud.create_event(session, title="客户对接", start_at=datetime(2026, 5, 31, 10, 0))
    crud.create_event(session, title="下周会", start_at=datetime(2026, 6, 3, 9, 0))
    llm = FakeLLM({"intent": "view", "time_expr": "这周"})
    r = handle_command("这周有什么安排", session=session, now=NOW, llm=llm)
    # 本周内 2 个（5/29、5/31），下周的不算
    assert "2" in r["speech"]
    assert "产品评审" in r["speech"] and "客户对接" in r["speech"]
    assert "下周会" not in r["speech"]
    # 跨天 → 带月日
    assert "5月29日" in r["speech"]
