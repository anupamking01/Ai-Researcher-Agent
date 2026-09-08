"""Small OpenAI chat-completion adapter used by the legacy application.

The project pins openai==0.27.10, so this module intentionally uses the
pre-1.0 ChatCompletion API. Streaming calls preserve the existing websocket
contract. Non-streaming calls can additionally record provider-reported token
usage for controlled experiments.
"""

from __future__ import annotations

from threading import Lock
from typing import Any, Iterable

import openai

from settings import Config


CFG = Config()


class UsageTracker:
    """Thread-safe accumulator for provider-reported ChatCompletion usage.

    The research agent summarizes multiple pages in a thread pool, so usage
    accounting must be safe when several non-streaming completions finish at
    nearly the same time. The tracker never estimates missing provider usage;
    it records such calls separately as unavailable.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._model_calls = 0
        self._unavailable_calls = 0
        self._by_model: dict[str, dict[str, int]] = {}

    @staticmethod
    def _usage_value(usage: Any, key: str) -> int:
        if usage is None:
            return 0
        try:
            value = usage.get(key, 0)
        except AttributeError:
            value = getattr(usage, key, 0)
        try:
            return max(int(value or 0), 0)
        except (TypeError, ValueError):
            return 0

    def _model_bucket(self, model: str) -> dict[str, int]:
        return self._by_model.setdefault(
            model,
            {
                "model_calls": 0,
                "unavailable_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )

    def record_response(self, model: str, response: Any) -> None:
        try:
            usage = response.get("usage")
        except AttributeError:
            usage = getattr(response, "usage", None)

        if not usage:
            self.record_unavailable(model)
            return

        prompt_tokens = self._usage_value(usage, "prompt_tokens")
        completion_tokens = self._usage_value(usage, "completion_tokens")
        total_tokens = self._usage_value(usage, "total_tokens")
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        with self._lock:
            self._model_calls += 1
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            bucket = self._model_bucket(model)
            bucket["model_calls"] += 1
            bucket["prompt_tokens"] += prompt_tokens
            bucket["completion_tokens"] += completion_tokens
            bucket["total_tokens"] += total_tokens

    def record_unavailable(self, model: str) -> None:
        with self._lock:
            self._model_calls += 1
            self._unavailable_calls += 1
            bucket = self._model_bucket(model)
            bucket["model_calls"] += 1
            bucket["unavailable_calls"] += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "model_calls": self._model_calls,
                "unavailable_calls": self._unavailable_calls,
                "prompt_tokens": self._prompt_tokens,
                "completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "by_model": {
                    model: dict(values) for model, values in self._by_model.items()
                },
            }


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
    )
    if usage_tracker is not None:
        usage_tracker.record_response(model, response)
    return _choice_content(response)
