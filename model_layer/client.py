from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from model_layer.config import ModelLayerConfig, load_config
from model_layer.middleware.base import ModelMiddleware
from model_layer.provider import ModelProvider, OpenAICompatibleProvider
from model_layer.router import ModelRouter
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


class ModelClient:
    """Unified entry for model calls: route -> middleware chain -> provider."""

    def __init__(
        self,
        router: ModelRouter,
        providers: dict[str, ModelProvider],
        middlewares: list[ModelMiddleware] | None = None,
    ) -> None:
        self._router = router
        self._providers = providers
        self._middlewares = middlewares or []

    @classmethod
    def from_config(cls, config: ModelLayerConfig | None = None) -> ModelClient:
        cfg = config or load_config()
        router = ModelRouter(cfg)
        providers: dict[str, ModelProvider] = {}
        for pid, pc in cfg.providers.items():
            if pc.type == "openai_compatible":
                providers[pid] = OpenAICompatibleProvider(pc)
            else:
                raise ValueError(f"Unsupported provider type: {pc.type}")

        middlewares: list[ModelMiddleware] = []
        from model_layer.middleware.metrics import MetricsMiddleware
        from model_layer.middleware.rate_limit import RateLimitMiddleware
        from model_layer.middleware.retry import RetryMiddleware

        metrics = MetricsMiddleware()
        rate_limit = RateLimitMiddleware()
        for task_name, tc in cfg.tasks.items():
            if tc.rate_limit_rpm:
                rate_limit.set_task_rpm(task_name, tc.rate_limit_rpm)

        middlewares.extend([rate_limit, RetryMiddleware(), metrics])
        client = cls(router, providers, middlewares)
        client._metrics_middleware = metrics  # type: ignore[attr-defined]
        return client

    def metrics_snapshot(self) -> dict[str, Any]:
        mw = getattr(self, "_metrics_middleware", None)
        if mw is not None:
            return mw.metrics.snapshot()
        return {}

    def _provider(self, route: ResolvedRoute) -> ModelProvider:
        prov = self._providers.get(route.provider_id)
        if prov is None:
            raise KeyError(f"Unknown provider '{route.provider_id}'")
        return prov

    def _chain_complete(
        self,
        req: ModelRequest,
        route: ResolvedRoute,
        inner: Callable[[], ModelResponse],
    ) -> ModelResponse:
        call: Callable[[], ModelResponse] = inner
        for mw in reversed(self._middlewares):
            next_call = call

            def _wrap(
                _mw=mw,
                _next=next_call,
                _req=req,
                _route=route,
            ) -> ModelResponse:
                return _mw.wrap_complete(_req, _route, _next)

            call = _wrap
        return call()

    def complete(self, req: ModelRequest) -> ModelResponse:
        route = self._router.resolve(req)

        def inner() -> ModelResponse:
            return self._provider(route).complete(route, req)

        return self._chain_complete(req, route, inner)

    def complete_structured(self, req: ModelRequest) -> ModelResponse:
        route = self._router.resolve(req)

        def inner() -> ModelResponse:
            return self._provider(route).complete_structured(route, req)

        return self._chain_complete(req, route, inner)

    def stream(self, req: ModelRequest) -> Iterator[Any]:
        """Stream chat completion chunks from the resolved provider."""
        route = self._router.resolve(req)

        def inner() -> Iterator[Any]:
            return self._provider(route).stream(route, req)

        call: Callable[[], Iterator[Any]] = inner
        for mw in reversed(self._middlewares):
            next_call = call

            def _wrap(
                _mw=mw,
                _next=next_call,
                _req=req,
                _route=route,
            ) -> Iterator[Any]:
                return _mw.wrap_stream(_req, _route, _next)

            call = _wrap
        return call()
