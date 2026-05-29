"""Azure Speech token 服务与端点单元测试。

全部脱离网络与真实时间：注入假 fetcher 计数取 token 次数，注入假时钟控制缓存过期。
遵 docs/复盘.md D-12，本机可跑。
"""

from fastapi.testclient import TestClient

from app.speech import SpeechError, SpeechTokenService


class _Clock:
    """可控假时钟。"""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def test_token_cached_within_ttl():
    """TTL 内重复取 token 应命中缓存，只真正 fetch 一次。"""
    clock = _Clock()
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return f"token-{calls['n']}"

    svc = SpeechTokenService(ttl_seconds=540, fetcher=fetcher, now_func=clock)
    first = svc.get_token()
    clock.advance(100)  # 仍在 540s TTL 内
    second = svc.get_token()

    assert first["token"] == "token-1"
    assert second["token"] == "token-1"  # 缓存命中，未刷新
    assert calls["n"] == 1


def test_token_refreshed_after_ttl():
    """超过 TTL 后应刷新，重新 fetch。"""
    clock = _Clock()
    calls = {"n": 0}

    def fetcher():
        calls["n"] += 1
        return f"token-{calls['n']}"

    svc = SpeechTokenService(ttl_seconds=540, fetcher=fetcher, now_func=clock)
    first = svc.get_token()
    clock.advance(600)  # 超过 540s
    second = svc.get_token()

    assert first["token"] == "token-1"
    assert second["token"] == "token-2"
    assert calls["n"] == 2


def test_token_includes_region():
    """返回结构包含 region，供浏览器 SDK 初始化用。"""
    svc = SpeechTokenService(fetcher=lambda: "tk")
    out = svc.get_token()
    assert out["token"] == "tk"
    assert "region" in out


def test_endpoint_returns_token(monkeypatch):
    """/api/speech/token 正常签发。"""
    from app.api import speech as speech_api

    fake = SpeechTokenService(fetcher=lambda: "browser-token")
    monkeypatch.setattr(speech_api, "get_token_service", lambda: fake)

    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post("/api/speech/token")
    assert resp.status_code == 200
    assert resp.json()["token"] == "browser-token"


def test_endpoint_503_when_not_configured(monkeypatch):
    """未配置 key（fetcher 抛 SpeechError）时端点返回 503，便于前端降级。"""
    from app.api import speech as speech_api

    def bad_fetch():
        raise SpeechError("AZURE_SPEECH_KEY 未配置")

    fake = SpeechTokenService(fetcher=bad_fetch)
    monkeypatch.setattr(speech_api, "get_token_service", lambda: fake)

    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post("/api/speech/token")
    assert resp.status_code == 503
