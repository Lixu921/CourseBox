"""进程内的固定窗口限流。

只用来拦住脚本级的突发流量：单进程、内存计数、按分钟窗口滚动。
多实例部署时每个实例各自计数，属已知取舍——这个规模不值得引入 Redis。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from starlette.requests import Request

WINDOW_SECONDS = 60
# 健康检查会被监控高频轮询，计入配额反而会让监控自己把站点刷到限流。
EXEMPT_PATHS = frozenset({"/接口/健康", "/api/health"})


@dataclass
class _Window:
    started_at: float
    count: int


class RateLimiter:
    """按 key（当前实现是客户端 IP）计数的固定窗口限流器。"""

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

    def hit(self, key: str, limit: int) -> tuple[bool, int]:
        """记录一次请求，返回 (是否放行, 建议重试的秒数)。"""

        now = time.monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= WINDOW_SECONDS:
                self._prune(now)
                self._windows[key] = _Window(started_at=now, count=1)
                return True, WINDOW_SECONDS
            window.count += 1
            retry_after = max(1, int(WINDOW_SECONDS - (now - window.started_at)) + 1)
            return window.count <= limit, retry_after

    def _prune(self, now: float) -> None:
        """开新窗口时顺手清掉过期条目，避免 IP 多了以后内存只涨不落。"""

        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started_at >= WINDOW_SECONDS
        ]
        for key in expired:
            self._windows.pop(key, None)


rate_limiter = RateLimiter()


def reset_rate_limits() -> None:
    """清空计数，让每个测试用例都从干净状态开始。"""

    rate_limiter.reset()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"
