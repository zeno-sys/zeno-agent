"""Unified user input for CLI and future HTTP/Web gateways."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.core.multimodal import build_openai_user_content


@dataclass(frozen=True)
class UserInput:
    text: str
    image_paths: tuple[Path, ...] = ()


def user_input_to_message(ui: UserInput) -> dict[str, Any]:
    return {
        "role": "user",
        "content": build_openai_user_content(ui.text, ui.image_paths),
    }
