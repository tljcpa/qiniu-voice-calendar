"""events REST 端点测试。

用 TestClient + 依赖覆盖把 get_session 指向共享内存库，脱网验证 HTTP 层。
"""

import pytest
from fastapi.testclient import TestClient

from app.db import Base, get_session, make_engine, make_session_factory
from app.main import create_app


@pytest.fixture()
def client():
    engine = make_engine("sqlite://")
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    def override_get_session():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session
    return TestClient(app)


def test_create_and_list_event(client):
    resp = client.post("/api/events", json={
        "title": "产品评审会",
        "start_at": "2026-05-30T15:00:00",
        "attendees": ["小王"],
    })
    assert resp.status_code == 201
    created = resp.json()
    assert created["title"] == "产品评审会"
    assert created["end_at"] == "2026-05-30T16:00:00"  # 默认 +1h

    listed = client.get("/api/events").json()
    assert len(listed) == 1
    assert listed[0]["attendees"] == ["小王"]


def test_list_with_range(client):
    client.post("/api/events", json={"title": "今天", "start_at": "2026-05-30T10:00:00"})
    client.post("/api/events", json={"title": "次日", "start_at": "2026-05-31T10:00:00"})
    resp = client.get("/api/events", params={
        "start": "2026-05-30T00:00:00",
        "end": "2026-05-30T23:59:59",
    })
    titles = [e["title"] for e in resp.json()]
    assert titles == ["今天"]


def test_update_event(client):
    ev = client.post("/api/events", json={"title": "会", "start_at": "2026-05-30T15:00:00"}).json()
    resp = client.patch(f"/api/events/{ev['id']}", json={"location": "会议室A"})
    assert resp.status_code == 200
    assert resp.json()["location"] == "会议室A"


def test_update_missing_404(client):
    resp = client.patch("/api/events/999", json={"title": "x"})
    assert resp.status_code == 404


def test_delete_event(client):
    ev = client.post("/api/events", json={"title": "会", "start_at": "2026-05-30T15:00:00"}).json()
    resp = client.delete(f"/api/events/{ev['id']}")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert client.get("/api/events").json() == []


def test_delete_missing_404(client):
    resp = client.delete("/api/events/999")
    assert resp.status_code == 404
