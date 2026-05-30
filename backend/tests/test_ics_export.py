"""测试 .ics 导出端点（创新3）。

覆盖：
  1. 无认证返回 401
  2. 各 range 参数正确生成 text/calendar
  3. .ics 内容包含期望的 VEVENT 字段
  4. voice_command._handle_export 正确映射 time_expr → range
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import create_token, hash_password
from app.db import Base, get_session
from app.main import create_app
from app.models import Event, User


@pytest.fixture()
def db_session(tmp_path):
    """内存 SQLite + 建表。"""
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client(db_session):
    """带测试 DB 的 TestClient。"""
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def user_token(db_session):
    """创建测试用户并返回 JWT。"""
    u = User(username="testuser", password_hash=hash_password("pw"))
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u.id, create_token(u.id)


@pytest.fixture()
def seeded(db_session, user_token):
    """插入一个本周内的事件。"""
    uid, _ = user_token
    now = datetime.now()
    ev = Event(
        owner_id=uid,
        title="测试会议",
        start_at=now.replace(hour=10, minute=0, second=0, microsecond=0),
        end_at=now.replace(hour=11, minute=0, second=0, microsecond=0),
    )
    db_session.add(ev)
    db_session.commit()
    return ev


def test_export_requires_auth(client):
    """未提供 token 应返回 401。"""
    resp = client.get("/api/calendar/export.ics")
    assert resp.status_code == 401


def test_export_week_returns_ics(client, user_token, seeded):
    """有效 token + range=week 应返回 text/calendar 且含事件。"""
    _, token = user_token
    resp = client.get(
        "/api/calendar/export.ics?range=week",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]
    body = resp.text
    assert "VCALENDAR" in body
    assert "VEVENT" in body
    assert "测试会议" in body


def test_export_token_query_param(client, user_token, seeded):
    """?token= query param 也应鉴权通过（webcal 订阅场景）。"""
    _, token = user_token
    resp = client.get(f"/api/calendar/export.ics?range=week&token={token}")
    assert resp.status_code == 200
    assert "VCALENDAR" in resp.text


def test_export_today_empty(client, user_token):
    """无事件时 .ics 仍然合法，仅无 VEVENT。"""
    _, token = user_token
    resp = client.get(
        "/api/calendar/export.ics?range=today",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "VCALENDAR" in resp.text
    assert "VEVENT" not in resp.text


def test_export_month(client, user_token, seeded):
    """range=month 应正常返回。"""
    _, token = user_token
    resp = client.get(
        "/api/calendar/export.ics?range=month",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "VCALENDAR" in resp.text


def test_export_invalid_range_falls_back_to_week(client, user_token):
    """未知 range 值降级为 week，不报错。"""
    _, token = user_token
    resp = client.get(
        "/api/calendar/export.ics?range=nonsense",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "VCALENDAR" in resp.text


# ---- voice_command._handle_export 单测 ----

def test_handle_export_week():
    from app.voice_command import _handle_export
    resp = _handle_export({"time_expr": "本周"})
    assert resp["intent"] == "export"
    assert resp["ok"] is True
    assert "week" in resp["export_url"]
    assert resp["export_label"] == "本周"


def test_handle_export_today():
    from app.voice_command import _handle_export
    resp = _handle_export({"time_expr": "今天"})
    assert "today" in resp["export_url"]
    assert resp["export_label"] == "今日"


def test_handle_export_month():
    from app.voice_command import _handle_export
    resp = _handle_export({"time_expr": "这个月"})
    assert "month" in resp["export_url"]
    assert resp["export_label"] == "本月"


def test_handle_export_no_time_expr():
    from app.voice_command import _handle_export
    resp = _handle_export({"time_expr": None})
    assert "week" in resp["export_url"]
