from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

from model_layer.middleware.base import ModelMiddleware
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


class RateLimitMiddleware(ModelMiddleware):
    '''滑动窗口速率限制中间件，按任务名称进行速率限制'''

    def __init__(self, default_rpm: int | None = None) -> None:
        self._default_rpm = default_rpm
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._per_task_rpm: dict[str, int] = {}

    def set_task_rpm(self, task: str, rpm: int) -> None:
        '''给指定任务的速率限制'''
        self._per_task_rpm[task] = rpm

    def _rpm_for(self, req: ModelRequest) -> int | None:
        '''获取指定任务的速率限制'''
        return self._per_task_rpm.get(req.task, self._default_rpm)

    def _check(self, req: ModelRequest) -> None:
        '''检查请求是否超过速率限制'''
        rpm = self._rpm_for(req)
        if rpm is None or rpm <= 0:
            return
        key = req.task
        now = time.time()
        window = now - 60
        self._timestamps[key] = [t for t in self._timestamps[key] if t > window]
        if len(self._timestamps[key]) >= rpm:
            raise RuntimeError(
                f"Model rate limit exceeded for task '{req.task}' ({rpm} requests/minute)"
            )
        self._timestamps[key].append(now)

    def wrap_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], ModelResponse],
    ) -> ModelResponse:
        '''包装完整请求，检查是否超过速率限制'''
        self._check(req)
        return call_next()

    def wrap_stream(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        '''包装流请求，检查是否超过速率限制'''
        self._check(req)
        return call_next()
