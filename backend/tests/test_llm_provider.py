"""LLM 抽象层单元测试。

全部用假对象，不触网、不需要真实凭证（遵 docs/复盘.md D-12，本机可跑）。
覆盖：文本补全、JSON 解析、json_mode 透传、主后端失败自动 fallback、全失败报错、无后端报错。
"""

import json

import pytest

from app.llm_provider import LLMError, LLMProvider, _Backend


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    """记录最后一次调用参数，并按预设返回或抛错。"""

    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self.error is not None:
            raise self.error
        return _FakeResponse(self.content)


class _FakeClient:
    def __init__(self, content=None, error=None):
        completions = _FakeCompletions(content=content, error=error)
        # 模拟 openai 客户端的 client.chat.completions.create 结构
        self.chat = type("Chat", (), {"completions": completions})()
        self._completions = completions


def _make_provider(backends):
    """绕过 __init__ 的凭证构造，直接注入假后端，专测编排逻辑。"""
    provider = LLMProvider.__new__(LLMProvider)
    provider.backends = backends
    return provider


def test_complete_returns_text():
    client = _FakeClient(content="你好")
    backend = _Backend("fake", client, "m")
    provider = _make_provider([backend])
    out = provider.complete([{"role": "user", "content": "hi"}])
    assert out == "你好"


def test_complete_json_parses_dict():
    payload = {"intent": "add", "title": "开会"}
    client = _FakeClient(content=json.dumps(payload, ensure_ascii=False))
    provider = _make_provider([_Backend("fake", client, "m")])
    out = provider.complete_json([{"role": "user", "content": "hi"}])
    assert out == payload


def test_json_mode_sets_response_format():
    client = _FakeClient(content="{}")
    provider = _make_provider([_Backend("fake", client, "m")])
    provider.complete_json([{"role": "user", "content": "hi"}])
    # 确认 json_mode 透传到底层调用
    assert client._completions.last_kwargs["response_format"] == {"type": "json_object"}


def test_fallback_to_second_backend_on_error():
    bad = _Backend("bad", _FakeClient(error=RuntimeError("限流")), "m")
    good = _Backend("good", _FakeClient(content="兜底成功"), "m")
    provider = _make_provider([bad, good])
    out = provider.complete([{"role": "user", "content": "hi"}])
    assert out == "兜底成功"


def test_all_backends_fail_raises():
    bad1 = _Backend("b1", _FakeClient(error=RuntimeError("x")), "m")
    bad2 = _Backend("b2", _FakeClient(error=RuntimeError("y")), "m")
    provider = _make_provider([bad1, bad2])
    with pytest.raises(LLMError):
        provider.complete([{"role": "user", "content": "hi"}])


def test_invalid_json_raises_llm_error():
    client = _FakeClient(content="这不是JSON")
    provider = _make_provider([_Backend("fake", client, "m")])
    with pytest.raises(LLMError):
        provider.complete_json([{"role": "user", "content": "hi"}])


def test_no_backend_configured_raises(monkeypatch):
    # 让两个 builder 都返回 None，模拟"忘了配 key"
    monkeypatch.setattr("app.llm_provider._build_deepseek", lambda: None)
    monkeypatch.setattr("app.llm_provider._build_azure", lambda: None)
    with pytest.raises(LLMError):
        LLMProvider()


def test_primary_name():
    provider = _make_provider([_Backend("deepseek", _FakeClient(content="x"), "m")])
    assert provider.primary_name() == "deepseek"
