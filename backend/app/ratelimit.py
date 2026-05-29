"""轻量内存限流（滑动窗口，按客户端 IP）。

公网 demo 的 /api 无鉴权，调用 LLM / Azure 的端点若被脚本刷会直接消耗
DeepSeek 余额与 Azure F0 配额。这里做一个进程内滑动窗口限流，挡住明显的滥刷，
对正常人类操作（每分钟几次）无感。

设计：
- 纯内存、单进程（单容器部署足够）；重启即清空，可接受。
- now_func 可注入，便于单测验证窗口滚动，不依赖真实时间。
"""

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    """滑动窗口限流：每个 key 在 window 秒内最多 max_calls 次。"""

    def __init__(
        self,
        max_calls: int,
        window: float,
        now_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_calls = max_calls
        self.window = window
        self._now = now_func
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """记录一次调用并返回是否放行。超限返回 False（不记入）。"""
        now = self._now()
        dq = self._hits[key]
        # 丢弃窗口外的旧时间戳
        cutoff = now - self.window
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self.max_calls:
            return False
        dq.append(now)
        return True


# 调用 LLM/Azure 的花费型端点：每 IP 每分钟 30 次（人类够用，挡脚本滥刷）。
_cost_limiter = RateLimiter(max_calls=30, window=60.0)


def _client_ip(request: Request) -> str:
    """取真实客户端 IP。Caddy 反代会带 X-Forwarded-For。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


def cost_rate_limit(request: Request) -> None:
    """FastAPI 依赖：花费型端点限流，超限抛 429。"""
    ip = _client_ip(request)
    if not _cost_limiter.allow(ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
