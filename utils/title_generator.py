"""Auto-generate short session titles from the first user/assistant exchange.

Runs asynchronously after the first response is delivered so it never
adds latency to the user-facing reply.
"""

import logging
import threading
from typing import Callable, Optional

def call_llm(
    task: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    timeout: float,
):
    """Route auxiliary LLM calls through the model layer."""
    from model_layer import ModelRequest, get_default_model_client
    from model_layer.types import TASK_AUXILIARY

    model_task = TASK_AUXILIARY if task in ("title_generation", "auxiliary") else task
    req = ModelRequest(
        task=model_task,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        metadata={"timeout": timeout},
    )
    return get_default_model_client().complete(req).raw

logger = logging.getLogger(__name__)

# Callback signature: (task_name, exception) -> None. Used to surface
# auxiliary failures to the user through AIAgent._emit_auxiliary_failure
# so silent-drops (e.g. OpenRouter 402 exhausting the fallback chain)
# become visible instead of piling up as NULL session titles.
FailureCallback = Callable[[str, BaseException], None]

_TITLE_PROMPT = (
    "Generate a short, descriptive title (3-7 words) for a conversation that starts with the "
    "following exchange. The title should capture the main topic or intent. "
    "Return ONLY the title text, nothing else. No quotes, no punctuation at the end, no prefixes."
)


def generate_title(
    user_message: str,
    assistant_response: str,
    timeout: float = 30.0,
    failure_callback: Optional[FailureCallback] = None,
) -> Optional[str]:
    """根据首次对话生成会话标题。

    使用辅助 LLM 客户端（最便宜/最快的可用模型）。
    返回标题字符串，如失败则返回 None。

    当辅助调用抛出异常时，会调用 ``failure_callback(task, exception)`` —— 通常由调用方连接至 ``AIAgent._emit_auxiliary_failure``，这样用户能看到告警，而不是会话无标题且无提示地累积。
    """
    # Truncate long messages to keep the request small
    user_snippet = user_message[:500] if user_message else ""
    assistant_snippet = assistant_response[:500] if assistant_response else ""

    messages = [
        {"role": "system", "content": _TITLE_PROMPT},
        {"role": "user", "content": f"User: {user_snippet}\n\nAssistant: {assistant_snippet}"},
    ]

    try:
        response = call_llm(
            task="title_generation",
            messages=messages,
            max_tokens=500,
            temperature=0.3,
            timeout=timeout,
        )
        title = (response.choices[0].message.content or "").strip()
        # Clean up: remove quotes, trailing punctuation, prefixes like "Title: "
        title = title.strip('"\'')
        if title.lower().startswith("title:"):
            title = title[6:].strip()
        # Enforce reasonable length
        if len(title) > 80:
            title = title[:77] + "..."
        return title if title else None
    except Exception as e:
        # Log at WARNING so this shows up in agent.log without debug mode.
        # Full detail at debug level for operators who need the stack.
        logger.warning("Title generation failed: %s", e)
        logger.debug("Title generation traceback", exc_info=True)
        if failure_callback is not None:
            try:
                failure_callback("title generation", e)
            except Exception:
                logger.debug("Title generation failure_callback raised", exc_info=True)
        return None


def auto_title_session(
    session_db,
    session_id: str,
    user_message: str,
    assistant_response: str,
    failure_callback: Optional[FailureCallback] = None,
) -> None:
    """若会话尚未设置标题，则自动生成并设置会话标题。

    在第一次问答交互完成后的后台线程中调用。
    满足如下任意条件将自动跳过：
    - session_db 为 None
    - 会话已有标题（用户手动设置，或已自动生成）
    - 标题生成失败
    """
    if not session_db or not session_id:
        return

    # Check if title already exists (user may have set one via /title before first response)
    try:
        existing = session_db.get_session_title(session_id)
        if existing:
            return
    except Exception:
        return

    title = generate_title(
        user_message, assistant_response, failure_callback=failure_callback
    )
    if not title:
        return

    try:
        session_db.set_session_title(session_id, title)
        logger.debug("Auto-generated session title: %s", title)
    except Exception as e:
        logger.debug("Failed to set auto-generated title: %s", e)


def maybe_auto_title(
    session_db,
    session_id: str,
    user_message: str,
    assistant_response: str,
    conversation_history: list,
    failure_callback: Optional[FailureCallback] = None,
) -> None:
    """仅在首次用户→助手交互后自动生成标题（异步，无需等待）。

    仅在满足如下条件时生成标题：
    - 当前为首次用户→助手对话
    - 尚未设置会话标题
    """
    if not session_db or not session_id or not user_message or not assistant_response:
        return

    # Count user messages in history to detect first exchange.
    # conversation_history includes the exchange that just happened,
    # so for a first exchange we expect exactly 1 user message
    # (or 2 counting system). Be generous: generate on first 2 exchanges.
    user_msg_count = sum(1 for m in (conversation_history or []) if m.get("role") == "user")
    if user_msg_count > 2:
        return

    thread = threading.Thread(
        target=auto_title_session,
        args=(session_db, session_id, user_message, assistant_response),
        kwargs={"failure_callback": failure_callback},
        daemon=True,
        name="auto-title",
    )
    thread.start()
