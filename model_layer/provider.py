from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, Protocol

from openai import OpenAI

from model_layer.config import ProviderConfig
from model_layer.types import ModelRequest, ModelResponse, ResolvedRoute


class ModelProvider(Protocol):
    def complete(self, route: ResolvedRoute, req: ModelRequest) -> ModelResponse: ...

    def stream(self, route: ResolvedRoute, req: ModelRequest) -> Iterator[Any]: ...

    def complete_structured(
        self, route: ResolvedRoute, req: ModelRequest
    ) -> ModelResponse: ...


class OpenAICompatibleProvider:
    """OpenAI SDK adapter for compatible HTTP APIs."""

    def __init__(self, config: ProviderConfig, *, client: OpenAI | None = None) -> None:
        self._config = config
        self._client = client or OpenAI(
            base_url=config.base_url or os.getenv("OPENAI_BASE_URL"),
            api_key=config.api_key or os.getenv("OPENAI_API_KEY"),
        )

    def _build_kwargs(self, route: ResolvedRoute, req: ModelRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": route.model,
            "messages": req.messages,
            "extra_body": dict(route.extra_body),
        }
        if req.tools:
            kwargs["tools"] = req.tools
        if req.max_tokens is not None:
            kwargs["max_tokens"] = req.max_tokens
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature
        return kwargs

    def complete(self, route: ResolvedRoute, req: ModelRequest) -> ModelResponse:
        kwargs = self._build_kwargs(route, req)
        raw = self._client.chat.completions.create(**kwargs)
        usage = getattr(raw, "usage", None)
        return ModelResponse(raw=raw, usage=usage)

    def stream(self, route: ResolvedRoute, req: ModelRequest) -> Iterator[Any]:
        kwargs = self._build_kwargs(route, req)
        kwargs["stream"] = True
        if route.include_stream_usage:
            kwargs["stream_options"] = {"include_usage": True}
        return self._client.chat.completions.create(**kwargs)

    def complete_structured(
        self, route: ResolvedRoute, req: ModelRequest
    ) -> ModelResponse:
        if req.response_format is None:
            raise ValueError("response_format required for structured completion")
        kwargs = self._build_kwargs(route, req)
        raw = self._client.beta.chat.completions.parse(
            response_format=req.response_format,
            **kwargs,
        )
        usage = getattr(raw, "usage", None)
        return ModelResponse(raw=raw, usage=usage)
