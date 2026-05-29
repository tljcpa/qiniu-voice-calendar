"""冲突检测与建议单元测试（内存库，脱网）。"""

from datetime import datetime, timedelta

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.conflict import check_conflict, find_overlaps, suggest_free_slot


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


def _add(session, title, h, m=0, dur_min=60):
    start = datetime(2026, 5, 30, h, m)
    return crud.create_event(
        session, title=title, start_at=start, end_at=start + timedelta(minutes=dur_min)
    )


def test_no_conflict_when_empty(session):
    r = check_conflict(session, datetime(2026, 5, 30, 15, 0), datetime(2026, 5, 30, 16, 0))
    assert r["has_conflict"] is False
    assert r["conflicts"] == []


def test_adjacent_not_conflict(session):
    """15:00 结束与 15:00 开始相邻，不算冲突（半开区间）。"""
    _add(session, "前一个", 14, dur_min=60)  # 14:00-15:00
    overlaps = find_overlaps(session, datetime(2026, 5, 30, 15, 0), datetime(2026, 5, 30, 16, 0))
    assert overlaps == []


def test_overlap_detected(session):
    _add(session, "客户对接", 15, dur_min=60)  # 15:00-16:00
    r = check_conflict(session, datetime(2026, 5, 30, 15, 30), datetime(2026, 5, 30, 16, 30))
    assert r["has_conflict"] is True
    assert len(r["conflicts"]) == 1
    assert r["conflicts"][0]["title"] == "客户对接"


def test_suggestion_is_after_conflict(session):
    """冲突时建议时段应不再冲突。"""
    _add(session, "客户对接", 15, dur_min=60)  # 15:00-16:00
    r = check_conflict(session, datetime(2026, 5, 30, 15, 0), datetime(2026, 5, 30, 16, 0))
    assert r["has_conflict"] is True
    assert r["suggestion"] is not None
    sug = datetime.fromisoformat(r["suggestion"])
    # 建议起点 >= 16:00（冲突事件结束），且本身无冲突
    assert sug >= datetime(2026, 5, 30, 16, 0)
    assert find_overlaps(session, sug, sug + timedelta(hours=1)) == []


def test_suggestion_skips_multiple_busy_slots(session):
    """连续占用时建议应跳到第一个真正空档。"""
    _add(session, "A", 15, dur_min=60)  # 15-16
    _add(session, "B", 16, dur_min=60)  # 16-17
    sug = suggest_free_slot(session, datetime(2026, 5, 30, 15, 0), datetime(2026, 5, 30, 16, 0))
    assert sug >= datetime(2026, 5, 30, 17, 0)


def test_exclude_self_in_update(session):
    """修改场景排除事件自身，不应与自己冲突。"""
    ev = _add(session, "会", 15, dur_min=60)
    overlaps = find_overlaps(
        session, ev.start_at, ev.end_at, exclude_id=ev.id
    )
    assert overlaps == []


def test_suggestion_rolls_to_next_day_when_evening_full(session):
    """晚间接近下班时间且后续被占满，建议滚到次日工作时段。"""
    # 占满 21:00-22:00，目标 21:30-22:30 超出工作时段上限
    _add(session, "晚会", 21, dur_min=60)
    sug = suggest_free_slot(
        session, datetime(2026, 5, 30, 21, 30), datetime(2026, 5, 30, 22, 30)
    )
    assert sug is not None
    # 应滚到次日 08:00 起
    assert sug.date() == datetime(2026, 5, 31).date()
    assert sug.time().hour >= 8
