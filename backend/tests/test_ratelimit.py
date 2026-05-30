"""限流与输入长度上限测试。脱网。"""

import pytest
from fastapi.testclient import TestClient

import app.ratelimit as ratelimit
from app.ratelimit import RateLimiter
from app.db import Base, get_session, make_engine, make_session_factory
from app.main import create_app


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


def test_allows_up_to_max_then_blocks():
    clock = _Clock()
    rl = RateLimiter(max_calls=3, window=60, now_func=clock)
    assert rl.allow("ip1") is True
    assert rl.allow("ip1") is True
    assert rl.allow("ip1") is True
    assert rl.allow("ip1") is False  # 第 4 次超限


def test_window_slides():
    clock = _Clock()
    rl = RateLimiter(max_calls=2, window=60, now_func=clock)
    assert rl.allow("ip") is True
    assert rl.allow("ip") is True
    assert rl.allow("ip") is False
    clock.advance(61)  # 窗口滚过
    assert rl.allow("ip") is True


def test_keys_isolated():
    clock = _Clock()
    rl = RateLimiter(max_calls=1, window=60, now_func=clock)
    assert rl.allow("a") is True
    assert rl.allow("b") is True  # 不同 IP 互不影响
    assert rl.allow("a") is False


@pytest.fixture()
def client(monkeypatch):
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
    # 用小额度限流器，便于验证 429
    monkeypatch.setattr(ratelimit, "_cost_limiter", RateLimiter(max_calls=2, window=60))
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"username": "bob", "password": "secret123"})
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return c


def test_command_rate_limited(client):
    # 前 2 次放行（无凭证 → 走 LLM 不可用的 200 兜底），第 3 次 429
    body = {"text": "今天有什么安排"}
    assert client.post("/api/voice/command", json=body).status_code == 200
    assert client.post("/api/voice/command", json=body).status_code == 200
    assert client.post("/api/voice/command", json=body).status_code == 429


def test_text_length_cap(client):
    long_text = "开会" * 200  # 远超 200 字符上限
    resp = client.post("/api/voice/command", json={"text": long_text})
    assert resp.status_code == 422  # pydantic 拒绝
