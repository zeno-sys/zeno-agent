from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from typing import Any

from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


class ModelMiddleware(ABC):
    @abstractmethod
    def wrap_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], ModelResponse],
    ) -> ModelResponse:
        ...

    def wrap_stream(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        call_next: Callable[[], Iterator[Any]],
    ) -> Iterator[Any]:
        return call_next()
