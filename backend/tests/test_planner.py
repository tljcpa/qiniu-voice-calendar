"""多轮规划 agent 测试（创新2）。FakeLLM 返回拆解项，验证避冲突与确认入库。脱网。"""

from datetime import datetime

import pytest

from app.db import Base, make_engine, make_session_factory
from app import crud
from app.voice_command import handle_command, handle_plan_confirm

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


PLAN_PAYLOAD = {
    "intent": "plan",
    "plan_items": [
        {"title": "论文复习", "time_expr": "下周一下午两点", "duration_minutes": 120},
        {"title": "论文复习", "time_expr": "下周三下午两点", "duration_minutes": 120},
        {"title": "论文复习", "time_expr": "下周五下午两点", "duration_minutes": 120},
    ],
}


def test_plan_proposes_multiple_items(session):
    r = handle_command("帮我安排下周三场论文复习每次两小时", session=session, now=NOW, llm=FakeLLM(PLAN_PAYLOAD))
    assert r["intent"] == "plan"
    assert r["needs_clarification"] is True  # 待确认，未入库
    assert len(r["pending_plan"]) == 3
    # 尚未创建
    assert crud.find_events(session, keyword="论文复习") == []
    # 下周一/三/五（2026-06-01/03/05）14:00
    starts = sorted(p["start_at"] for p in r["pending_plan"])
    assert starts[0].startswith("2026-06-01T14:00")
    assert starts[2].startswith("2026-06-05T14:00")


def test_plan_avoids_existing_conflict(session):
    # 下周一 14:00 已有会 → 该项应被避让到别的时段
    crud.create_event(session, title="组会", start_at=datetime(2026, 6, 1, 14, 0))
    r = handle_command("安排下周三场论文复习每次两小时", session=session, now=NOW, llm=FakeLLM(PLAN_PAYLOAD))
    mon = [p for p in r["pending_plan"] if p["start_at"].startswith("2026-06-01")]
    assert mon and mon[0]["adjusted"] is True
    # 避让后不再撞 14:00 组会
    assert not mon[0]["start_at"].startswith("2026-06-01T14:00")


def test_plan_items_dont_overlap_each_other(session):
    # 三项都给同一时段 → 应互相错开，无两项重叠
    same = {"intent": "plan", "plan_items": [
        {"title": "复习", "time_expr": "下周一下午两点", "duration_minutes": 60},
        {"title": "复习", "time_expr": "下周一下午两点", "duration_minutes": 60},
        {"title": "复习", "time_expr": "下周一下午两点", "duration_minutes": 60},
    ]}
    r = handle_command("安排下周一三场复习", session=session, now=NOW, llm=FakeLLM(same))
    iv = sorted((p["start_at"], p["end_at"]) for p in r["pending_plan"])
    for i in range(len(iv) - 1):
        assert iv[i][1] <= iv[i + 1][0]  # 前一项结束 <= 后一项开始，不重叠


def test_plan_confirm_creates_all(session):
    r = handle_command("安排下周三场论文复习", session=session, now=NOW, llm=FakeLLM(PLAN_PAYLOAD))
    plan = r["pending_plan"]
    r2 = handle_plan_confirm(plan, session=session, owner_id=None)
    assert r2["ok"] is True
    assert "3" in r2["speech"]
    assert len(crud.find_events(session, keyword="论文复习")) == 3
