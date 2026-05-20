from __future__ import annotations

import os

from model_layer.config import ModelLayerConfig, TaskConfig
from model_layer.types import (
    TASK_AGENT,
    TASK_ALIASES,
    ModelRequest,
    ResolvedRoute,
)


class ModelRouter:
    def __init__(self, config: ModelLayerConfig) -> None:
        self._config = config

    def _normalize_task(self, task: str) -> str:
        return TASK_ALIASES.get(task, task)

    def _task_config(self, task: str) -> TaskConfig:
        normalized = self._normalize_task(task)
        tc = self._config.tasks.get(normalized)
        if tc is None:
            tc = self._config.tasks.get(TASK_AGENT)
        if tc is None:
            raise ValueError(f"No task config for '{task}' and no agent fallback")
        return tc

    def resolve(self, req: ModelRequest) -> ResolvedRoute:
        tc = self._task_config(req.task)
        model = req.model or tc.model or os.getenv("MODEL_NAME", "")
        if not model:
            raise ValueError(f"No model resolved for task '{req.task}'")

        extra_body: dict = {}
        provider = self._config.providers.get(tc.provider)
        if provider:
            extra_body.update(provider.default_extra_body)
        extra_body.update(tc.extra_body)

        session_id = req.metadata.get("session_id")
        if session_id is not None and req.task in (TASK_AGENT, "agent"):
            extra_body.setdefault("session_id", session_id)

        include_usage = os.getenv("OPENAI_STREAM_INCLUDE_USAGE", "").lower() in (
            "1",
            "true",
            "yes",
        )

        return ResolvedRoute(
            provider_id=tc.provider,
            model=model,
            extra_body=extra_body,
            include_stream_usage=include_usage and bool(req.stream),
        )

    def rate_limit_rpm(self, req: ModelRequest) -> int | None:
        tc = self._task_config(req.task)
        return tc.rate_limit_rpm
