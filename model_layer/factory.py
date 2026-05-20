from __future__ import annotations

from model_layer.client import ModelClient

_default_client: ModelClient | None = None


def get_default_model_client() -> ModelClient:
    global _default_client
    if _default_client is None:
        _default_client = ModelClient.from_config()
    return _default_client


def reset_default_model_client(client: ModelClient | None = None) -> None:
    """Reset singleton (for tests). Pass client to inject a custom instance."""
    global _default_client
    _default_client = client
