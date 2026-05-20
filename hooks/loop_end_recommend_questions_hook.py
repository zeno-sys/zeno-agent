import json
from typing import Any

from pydantic import BaseModel, Field

from agent.core.multimodal import content_to_text
from agent.hook.schema import LoopEndHook
from model_layer import ModelRequest, get_default_model_client
from model_layer.types import TASK_STRUCTURED
from utils.pretty_print import print_recommended_questions


class RecommendQuestions(BaseModel):
    questions: list[str] = Field(default_factory=list, min_length=3, max_length=3, description="下一轮推荐问题")


class LoopEndRecommendQuestionsHook(LoopEndHook):
    """Loop结束时基于最近对话生成下一轮推荐问题。"""

    def invoke(self,context: Any) -> None:
        state = context.state
        messages = state.messages or []
        recent_pairs = self._collect_recent_user_ai_messages(messages, keep=5)
        if not recent_pairs:
            return

        recommended_questions = self._generate_recommended_questions(recent_pairs)
        if not recommended_questions:
            return

        print_recommended_questions(recommended_questions, max_count=3)

    def _collect_recent_user_ai_messages(
        self,
        messages: list[dict[str, Any]],
        keep: int = 5,
    ) -> list[dict[str, str]]:
        filtered: list[dict[str, str]] = []
        for message in messages:
            role = message.get("role")
            if role not in ("user", "assistant"):
                continue

            if role == "assistant" and message.get("tool_calls"):
                continue

            text = content_to_text(message.get("content")).strip()
            if not text:
                continue

            filtered.append({"role": role, "content": text})

        return filtered[-keep:]

    def _generate_recommended_questions(
        self,
        recent_pairs: list[dict[str, str]],
    ) -> list[str]:
        prompt_payload = json.dumps(recent_pairs, ensure_ascii=False, indent=2)
        messages = [
            {
                "role": "system",
                "content": (
                    "你是对话引导助手。请基于给定的最近对话，生成3条简短、自然、可直接提问的下一轮问题。注意：不要加编号，不要解释。"
                ),
            },
            {
                "role": "user",
                "content": f"最近对话如下（仅 user/assistant）：\n{prompt_payload}",
            },
        ]

        try:
            model_req = ModelRequest(
                task=TASK_STRUCTURED,
                messages=messages,
                response_format=RecommendQuestions,
            )
            response = get_default_model_client().complete_structured(model_req)
            content: RecommendQuestions | None = response.message.parsed
        except Exception:
            return []
        return content.questions
