"""Azure Speech 服务封装。

职责（见 docs/复盘.md D-14）：
1. 短时 token 签发（核心）：浏览器 Azure JS SDK 拿 token 直连 Azure 做流式 ASR/TTS，
   key 留在后端绝不下发。token 约 10 分钟有效，本地缓存复用以降延迟、省配额。
2. 服务端 TTS 合成（验证/降级）：把文案合成为音频字节，azure SDK 懒加载。

token 签发只用 httpx 发一个 POST，不引入重型 azure SDK，便于 mock 单测（遵 D-12）。
"""

import time
from typing import Callable, Optional

import httpx

from app.config import settings


class SpeechError(Exception):
    """Azure Speech 相关错误。"""


def _default_fetch_token() -> str:
    """向 Azure issueToken 端点换取短时 token（默认实现）。

    单独成函数便于测试时替换。失败抛 SpeechError。
    """
    if not settings.azure_speech_key:
        raise SpeechError("AZURE_SPEECH_KEY 未配置，无法签发语音 token")

    url = (
        f"https://{settings.azure_speech_region}"
        ".api.cognitive.microsoft.com/sts/v1.0/issueToken"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
        "Content-Length": "0",
    }
    try:
        resp = httpx.post(url, headers=headers, timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise SpeechError(f"获取 Azure Speech token 失败：{exc}") from exc
    return resp.text


class SpeechTokenService:
    """短时 token 签发与缓存。

    为可测性，时间源 now_func 与取 token 的 fetcher 都可注入：
    测试时传入假 fetcher 与假时钟即可验证缓存命中与过期刷新，完全脱离网络与真实时间。
    """

    def __init__(
        self,
        ttl_seconds: float = 540.0,
        fetcher: Optional[Callable[[], str]] = None,
        now_func: Callable[[], float] = time.monotonic,
    ) -> None:
        # 540s = 9 分钟 < Azure token 10 分钟有效期，留 1 分钟安全余量避免边界失效。
        self._ttl = ttl_seconds
        if fetcher is None:
            self._fetch = _default_fetch_token
        else:
            self._fetch = fetcher
        self._now = now_func

        self._token: Optional[str] = None
        self._fetched_at: float = 0.0

    def get_token(self) -> dict:
        """返回 {token, region}。缓存未过期则复用，否则刷新。"""
        now = self._now()
        cache_valid = self._token is not None and (now - self._fetched_at) < self._ttl
        if cache_valid:
            return {"token": self._token, "region": settings.azure_speech_region}

        token = self._fetch()
        self._token = token
        self._fetched_at = now
        return {"token": token, "region": settings.azure_speech_region}


def synthesize_speech(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> bytes:
    """服务端 TTS：把文案合成为音频字节（验证/降级用）。

    懒加载 azure SDK：未安装时只在调用本函数时报错，不影响 token 签发与其它模块。
    默认音色 XiaoxiaoNeural（自然女声，中文 demo 常用）。
    """
    if not settings.azure_speech_key:
        raise SpeechError("AZURE_SPEECH_KEY 未配置，无法合成语音")
    try:
        import azure.cognitiveservices.speech as speechsdk
    except ImportError as exc:
        raise SpeechError(
            "未安装 azure-cognitiveservices-speech，无法服务端合成语音"
        ) from exc

    speech_config = speechsdk.SpeechConfig(
        subscription=settings.azure_speech_key,
        region=settings.azure_speech_region,
    )
    speech_config.speech_synthesis_voice_name = voice
    # 不绑定音频输出设备，直接拿内存中的音频字节（适合服务端返回/写文件）。
    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config, audio_config=None
    )
    result = synthesizer.speak_text_async(text).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise SpeechError(f"TTS 合成失败：reason={result.reason}")
    return result.audio_data


# 进程级 token 服务单例。
_token_service: Optional[SpeechTokenService] = None


def get_token_service() -> SpeechTokenService:
    """获取全局 token 服务单例。"""
    global _token_service
    if _token_service is None:
        _token_service = SpeechTokenService()
    return _token_service
