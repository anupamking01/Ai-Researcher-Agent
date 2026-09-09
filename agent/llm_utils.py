"""Small OpenAI chat-completion adapter used by the legacy application.

The project pins openai==0.27.10, so this module intentionally uses the
pre-1.0 ChatCompletion API. Streaming calls preserve the existing websocket
contract. Non-streaming calls can additionally record provider-reported token
usage for controlled experiments.
"""

from __future__ import annotations

from typing import Any, Iterable

import openai

from logic.usage import UsageTracker
from settings import Config


CFG = Config()
# A synchronous provider request must not be able to block the event loop or a
# source-summary worker forever. This is an infrastructure guardrail; the
# higher-level pilot also has per-source and per-run timeouts.
OPENAI_REQUEST_TIMEOUT_SECONDS = 120


def _choice_content(response: Any) -> str:
    """Extract assistant text from an OpenAI 0.x ChatCompletion response."""
    try:
        return response["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


async def _stream_completion(
    *,
    model: str,
    messages: Iterable[dict],
    websocket: Any,
    temperature: float,
    usage_tracker: UsageTracker | None = None,
) -> str:
    response = openai.ChatCompletion.create(
        model=model,
        messages=list(messages),
        temperature=temperature,
        stream=True,
        request_timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
    )

    # openai==0.27.10 streaming responses do not reliably expose a final usage
    # object. Mark the call unavailable rather than manufacturing token counts.
    if usage_tracker is not None:
        usage_tracker.record_unavailable(model)

    parts: list[str] = []
    for chunk in response:
        try:
            delta = chunk["choices"][0]["delta"].get("content", "")
        except (KeyError, IndexError, AttributeError, TypeError):
            delta = ""

        if not delta:
            continue

        parts.append(delta)
        if websocket is not None:
            if hasattr(websocket, "send_text"):
                await websocket.send_text(delta)
            elif hasattr(websocket, "send_json"):
                await websocket.send_json({"type": "report", "output": delta})

    return "".join(parts)


def create_chat_completion(
    *,
    model: str,
    messages: Iterable[dict],
    stream: bool = False,
    websocket: Any = None,
    temperature: float | None = None,
    usage_tracker: UsageTracker | None = None,
):
    """Create a chat completion using the repository's pinned OpenAI client."""
    resolved_temperature = CFG.temperature if temperature is None else temperature

    if stream:
        return _stream_completion(
            model=model,
            messages=messages,
            websocket=websocket,
            temperature=resolved_temperature,
            usage_tracker=usage_tracker,
        )

    response = openai.ChatCompletion.create(
        model=model,
        messages=list(messages),
        temperature=resolved_temperature,
        request_timeout=OPENAI_REQUEST_TIMEOUT_SECONDS,
    )
    if usage_tracker is not None:
        usage_tracker.record_response(model, response)
    return _choice_content(response)
