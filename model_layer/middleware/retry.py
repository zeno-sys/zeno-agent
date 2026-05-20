from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

from model_layer.middleware.base import ModelMiddleware
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) if response else None
    if status in _RETRYABLE_STATUS:
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "timeout" in msg or "503" in msg


class RetryMiddleware(ModelMiddleware):
    """Exponential backoff for non-streaming completions only."""

    def __init__(self, max_attempts: int = 3, base_delay: float = 0.5) -> None:
        self._max_attempts = max(1, max_attempts)
        self._base_delay = base_delay

    def wrap_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], ModelResponse],
    ) -> ModelResponse:
        last_exc: BaseException | None = None
        for attempt in range(self._max_attempts):
            try:
                return call_next()
            except Exception as exc:
                last_exc = exc
                if attempt >= self._max_attempts - 1 or not _is_retryable(exc):
                    raise
                time.sleep(self._base_delay * (2**attempt))
        assert last_exc is not None
        raise last_exc

    def wrap_stream(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        # Streaming retry is not attempted (would require buffering).
        return call_next()
