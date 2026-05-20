from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from model_layer.middleware.base import ModelMiddleware
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


@dataclass
class ModelMetrics:
    requests: int = 0
    errors: int = 0
    tokens_used: int = 0
    by_task: dict[str, dict[str, int]] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "errors": self.errors,
            "tokens_used": self.tokens_used,
            "by_task": dict(self.by_task),
        }


class MetricsMiddleware(ModelMiddleware):
    def __init__(self) -> None:
        self.metrics = ModelMetrics()

    def _bump_task(self, task: str, field_name: str, n: int = 1) -> None:
        bucket = self.metrics.by_task.setdefault(
            task, {"requests": 0, "errors": 0, "tokens_used": 0}
        )
        bucket[field_name] = bucket.get(field_name, 0) + n

    def _record_usage(self, req: ModelRequest, usage: Any) -> None:
        if usage is None:
            return
        total = getattr(usage, "total_tokens", None)
        if isinstance(total, int):
            self.metrics.tokens_used += total
            self._bump_task(req.task, "tokens_used", total)

    def wrap_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], ModelResponse],
    ) -> ModelResponse:
        self.metrics.requests += 1
        self._bump_task(req.task, "requests")
        try:
            resp = call_next()
            self._record_usage(req, resp.usage)
            return resp
        except Exception:
            self.metrics.errors += 1
            self._bump_task(req.task, "errors")
            raise

    def wrap_stream(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        self.metrics.requests += 1
        self._bump_task(req.task, "requests")
        try:
            for chunk in call_next():
                u = getattr(chunk, "usage", None)
                if u is not None:
                    self._record_usage(req, u)
                yield chunk
        except Exception:
            self.metrics.errors += 1
            self._bump_task(req.task, "errors")
            raise
