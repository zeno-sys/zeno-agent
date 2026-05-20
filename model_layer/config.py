from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return os.getenv(match.group(1), "")

    return _ENV_PATTERN.sub(repl, value)


def _expand_dict(obj: Any) -> Any:
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _expand_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_dict(v) for v in obj]
    return obj


@dataclass
class TaskConfig:
    provider: str = "default"
    model: str | None = None
    stream: bool | None = None
    max_tokens: int | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)
    rate_limit_rpm: int | None = None


@dataclass
class ProviderConfig:
    type: str = "openai_compatible"
    base_url: str | None = None
    api_key: str | None = None
    default_extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelLayerConfig:
    tasks: dict[str, TaskConfig] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)


def _default_config() -> ModelLayerConfig:
    model_name = os.getenv("MODEL_NAME", "")
    auxiliary_model = os.getenv("MODEL_AUXILIARY_NAME") or model_name
    base_url = os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")

    default_provider = ProviderConfig(
        type="openai_compatible",
        base_url=base_url,
        api_key=api_key,
        default_extra_body={"enable_thinking": False},
    )

    include_usage = os.getenv("OPENAI_STREAM_INCLUDE_USAGE", "").lower() in (
        "1",
        "true",
        "yes",
    )

    return ModelLayerConfig(
        tasks={
            "agent": TaskConfig(
                provider="default",
                model=model_name or None,
                stream=True,
                extra_body={"enable_thinking": False},
            ),
            "auxiliary": TaskConfig(
                provider="default",
                model=auxiliary_model or None,
                stream=False,
                max_tokens=500,
                extra_body={"enable_thinking": False},
            ),
            "structured": TaskConfig(
                provider="default",
                model=model_name or None,
                stream=False,
                extra_body={"enable_thinking": False},
            ),
        },
        providers={"default": default_provider},
    )


def load_config(path: str | Path | None = None) -> ModelLayerConfig:
    """Load config from YAML if path set, else env defaults."""
    config_path = path or os.getenv("MODEL_LAYER_CONFIG")
    if not config_path:
        return _default_config()

    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    raw = _expand_dict(raw)

    tasks: dict[str, TaskConfig] = {}
    for name, tc in (raw.get("tasks") or {}).items():
        tasks[name] = TaskConfig(
            provider=tc.get("provider", "default"),
            model=tc.get("model"),
            stream=tc.get("stream"),
            max_tokens=tc.get("max_tokens"),
            extra_body=dict(tc.get("extra_body") or {}),
            rate_limit_rpm=tc.get("rate_limit_rpm"),
        )

    providers: dict[str, ProviderConfig] = {}
    for name, pc in (raw.get("providers") or {}).items():
        providers[name] = ProviderConfig(
            type=pc.get("type", "openai_compatible"),
            base_url=pc.get("base_url"),
            api_key=pc.get("api_key"),
            default_extra_body=dict(pc.get("default_extra_body") or {}),
        )

    if not providers:
        return _default_config()
    if not tasks:
        base = _default_config()
        base.providers = providers
        return base

    cfg = ModelLayerConfig(tasks=tasks, providers=providers)
    # Ensure agent task exists
    if "agent" not in cfg.tasks:
        cfg.tasks["agent"] = _default_config().tasks["agent"]
    return cfg
