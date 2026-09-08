"""Small OpenAI chat-completion adapter used by the legacy application.

The project pins openai==0.27.10, so this module intentionally uses the
pre-1.0 ChatCompletion API.  Streaming calls return an awaitable that emits
text to the supplied websocket and resolves to the complete generated text;
non-streaming calls return a plain string.  This preserves the calling
contract used throughout the existing application.
"""

from __future__ import annotations

from typing import Any, Iterable

import openai

from settings import Config


CFG = Config()


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
) -> str:
    response = openai.ChatCompletion.create(
        model=model,
        messages=list(messages),
        temperature=temperature,
        stream=True,
    )

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
):
    """Create a chat completion using the repository's pinned OpenAI client.

    Token/cost accounting is deliberately not inferred here because the
    legacy streaming response does not expose a reliable usage object.  The
    experiment layer therefore records usage as unavailable rather than
    manufacturing token counts.
    """
    resolved_temperature = CFG.temperature if temperature is None else temperature

    if stream:
        return _stream_completion(
            model=model,
            messages=messages,
            websocket=websocket,
            temperature=resolved_temperature,
        )

    response = openai.ChatCompletion.create(
        model=model,
        messages=list(messages),
        temperature=resolved_temperature,
    )
    return _choice_content(response)
