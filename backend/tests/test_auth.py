"""账户认证与按用户作用域测试（创新1）。脱网。"""

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password, verify_password, create_token, decode_token
from app.db import Base, get_session, make_engine, make_session_factory
from app.main import create_app


@pytest.fixture()
def client():
    engine = make_engine("sqlite://")
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    def override():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    app = create_app()
    app.dependency_overrides[get_session] = override
    return TestClient(app)


def _auth_headers(c, username):
    r = c.post("/api/auth/register", json={"username": username, "password": "secret123"})
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_password_hash_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"  # 不存明文
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_token_roundtrip():
    assert decode_token(create_token(42)) == 42
    assert decode_token("garbage") is None


def test_register_login_flow(client):
    r = client.post("/api/auth/register", json={"username": "carol", "password": "secret123"})
    assert r.status_code == 201 and "token" in r.json()
    # 重复用户名 → 409
    assert client.post("/api/auth/register", json={"username": "carol", "password": "secret123"}).status_code == 409
    # 登录正确 → token；错误 → 401
    assert client.post("/api/auth/login", json={"username": "carol", "password": "secret123"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "carol", "password": "bad"}).status_code == 401


def test_endpoints_require_auth(client):
    assert client.get("/api/events").status_code == 401
    assert client.post("/api/events", json={"title": "x", "start_at": "2026-06-01T10:00:00"}).status_code == 401


def test_events_scoped_per_user(client):
    h1 = _auth_headers(client, "u1")
    h2 = _auth_headers(client, "u2")
    # u1 建事件
    client.post("/api/events", json={"title": "u1的会", "start_at": "2026-06-01T10:00:00"}, headers=h1)
    # u1 看得到，u2 看不到
    assert len(client.get("/api/events", headers=h1).json()) == 1
    assert client.get("/api/events", headers=h2).json() == []


def test_cannot_delete_others_event(client):
    h1 = _auth_headers(client, "a1")
    h2 = _auth_headers(client, "a2")
    ev = client.post("/api/events", json={"title": "私密", "start_at": "2026-06-01T10:00:00"}, headers=h1).json()
    # u2 删 u1 的事件 → 404（作用域隔离，等同不存在）
    assert client.delete(f"/api/events/{ev['id']}", headers=h2).status_code == 404
    # u1 仍能删自己的
    assert client.delete(f"/api/events/{ev['id']}", headers=h1).status_code == 200
