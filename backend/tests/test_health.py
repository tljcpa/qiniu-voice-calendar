"""PR1 冒烟测试：确认应用可构造、核心端点可响应。

用 FastAPI TestClient（基于 httpx）直接打内存中的 app，不需真正起服务。
这保证了"main 分支始终可运行"——CI 可用这一条快速验证。
"""

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_root_returns_service_info():
    """根路由返回服务标识。"""
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "voice-calendar-backend"
    assert "version" in body


def test_health_ok():
    """健康检查返回 status=ok，并报告依赖配置状态。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    # dependencies 字段必须存在且为布尔，不泄露 key 内容。
    deps = body["dependencies"]
    assert isinstance(deps["azure_speech"], bool)
    assert isinstance(deps["llm"], bool)
