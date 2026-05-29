"""LLM 抽象层。

封装两个 OpenAI 兼容后端，对上层（意图解析 / 实体抽取 / 歧义澄清）暴露统一接口：

- DeepSeek（默认）：通过 openai-python 的 base_url 覆盖直连。
- Azure OpenAI（备用）：通过 AzureOpenAI 客户端。

设计要点（见 docs/复盘.md D-13）：
- 上层只调 complete() / complete_json()，不关心底层是哪家。
- complete_json() 用 response_format=json_object 强约束结构化输出，意图解析强依赖此能力。
- 主后端异常（网络/限流/余额）时自动 fallback 到另一后端重试一次，保证 demo 不因单点挂。
- 不引入 LangChain：直接用 openai-python，调试链路短、可控。
"""

import json
from typing import Optional

from app.config import settings


class LLMError(Exception):
    """LLM 调用失败（两个后端都失败时抛出）。"""


class _Backend:
    """单个后端的封装。持有一个 openai 客户端与其默认模型名。"""

    def __init__(self, name: str, client, model: str) -> None:
        self.name = name
        self.client = client
        self.model = model

    def complete(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """调用 chat completions，返回首条回复的文本内容。"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            # OpenAI 协议的 JSON mode：强制模型输出可解析的 JSON 对象。
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content


def _build_deepseek() -> Optional[_Backend]:
    """构造 DeepSeek 后端；凭证缺失返回 None。"""
    if not settings.deepseek_api_key:
        return None
    # 延迟 import，未装 openai 时不影响其它模块导入（如纯 health 测试）。
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )
    return _Backend("deepseek", client, settings.deepseek_model)


def _build_azure() -> Optional[_Backend]:
    """构造 Azure OpenAI 后端；凭证缺失返回 None。"""
    if not settings.azure_openai_api_key:
        return None
    if not settings.azure_openai_endpoint:
        return None
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_key=settings.azure_openai_api_key,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
    )
    # Azure 用"部署名"作为 model 路由标识。
    return _Backend("azure", client, settings.azure_openai_deployment)


class LLMProvider:
    """对上层暴露的统一 LLM 接口。

    按配置选主后端，另一个作 fallback。两个后端都不可用时构造即报错，
    便于在启动期就发现"忘了配 key"，而不是等到第一次调用。
    """

    def __init__(self, primary: Optional[str] = None) -> None:
        if primary is None:
            primary = settings.llm_backend

        builders = {
            "deepseek": _build_deepseek,
            "azure": _build_azure,
        }

        # 按"主后端在前"的顺序构造可用后端链。
        order = []
        if primary in builders:
            order.append(primary)
        for name in builders:
            if name not in order:
                order.append(name)

        self.backends: list[_Backend] = []
        for name in order:
            backend = builders[name]()
            if backend is not None:
                self.backends.append(backend)

        if not self.backends:
            raise LLMError(
                "没有可用的 LLM 后端：请配置 DEEPSEEK_API_KEY 或 AZURE_OPENAI_API_KEY"
            )

    def complete(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> str:
        """文本补全。依次尝试后端，全失败抛 LLMError。

        默认低温 0.2：意图/实体抽取要稳定可复现，不要发散。
        """
        last_error: Optional[Exception] = None
        for backend in self.backends:
            try:
                return backend.complete(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            except Exception as exc:  # noqa: BLE001 - 故意兜底以触发 fallback
                last_error = exc
                continue
        raise LLMError(f"所有 LLM 后端均失败，最后错误：{last_error}")

    def complete_json(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> dict:
        """结构化补全：强制 JSON mode 并解析为 dict。

        若模型返回的不是合法 JSON（极少见，JSON mode 已强约束），抛 LLMError。
        """
        raw = self.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise LLMError(f"LLM 返回非合法 JSON：{raw!r}") from exc

    def primary_name(self) -> str:
        """当前主后端名（首个可用后端）。用于日志与健康检查。"""
        return self.backends[0].name


# 进程级懒加载单例：首次使用时才构造，避免 import 期就要求凭证。
_provider: Optional[LLMProvider] = None


def get_llm() -> LLMProvider:
    """获取全局 LLMProvider 单例。"""
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider
