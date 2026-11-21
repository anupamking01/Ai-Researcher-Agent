"""Small OpenAI chat-completion adapter used by the legacy application.

The project pins openai==0.27.10, so this module intentionally uses the
pre-1.0 ChatCompletion API. Streaming calls preserve the existing websocket
contract. Non-streaming calls can additionally record provider-reported token
usage for controlled experiments.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import openai

from logic.usage import UsageTracker
from settings import Config


CFG = Config()
# Default timeout for planner/report/verifier calls. Source summarization uses a
# shorter explicit timeout because it is nested inside a per-source guardrail.
# Keeping the provider timeout below the experiment run timeout prevents a
# single request from blocking an entire pilot indefinitely while allowing the
# larger Terra report calls enough time to finish on hosted CI.
OPENAI_REQUEST_TIMEOUT_SECONDS = 150


def _validate_finish_reason(choice: Any, *, source: str) -> None:
    """Reject a provider-declared truncated or non-text completion.

    A missing/None reason is retained for older provider envelopes, but an
    explicit reason other than 'stop' must not certify a research report as
    successfully completed (e.g. 'length' or 'content_filter').
    """
    try:
        try:
            reason = choice.get("finish_reason", None)
        except AttributeError:
            reason = getattr(choice, "finish_reason", None)
    except Exception as exc:
        raise ValueError(f"provider {source} finish_reason is unreadable") from exc
    if reason is not None and (type(reason) is not str or reason != "stop"):
        raise ValueError(f"provider {source} finish_reason is not normal completion")


def _choice_content(response: Any) -> str:
    """Require a well-formed textual completion rather than fabricating an empty one.

    A genuinely empty text response is valid, but a missing or non-text
    response is a failed output, not evidence that the model answered "".
    """
    try:
        choice = response["choices"][0]
        content = choice["message"]["content"]
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise ValueError("provider response missing a textual assistant message") from exc
    if not isinstance(content, str):
        raise ValueError("provider response assistant content must be text")
    _validate_finish_reason(choice, source="completion")
    return content


async def _stream_completion(
    *,
    model: str,
    messages: Iterable[dict],
    websocket: Any,
    temperature: float,
    usage_tracker: UsageTracker | None = None,
    request_timeout_seconds: float = OPENAI_REQUEST_TIMEOUT_SECONDS,
) -> str:
    # A one-pass local message producer can fail before the provider is called.
    # Prepare the payload outside the provider-attempt accounting boundary.
    prepared_messages = list(messages)
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=prepared_messages,
            temperature=temperature,
            stream=True,
            request_timeout=request_timeout_seconds,
        )
    except Exception:
        # Invocation was attempted, but no usage receipt was returned.
        # Its provider billing/processing status is unknown, not zero.
        if usage_tracker is not None:
            usage_tracker.record_unavailable(model)
        raise

    # openai==0.27.10 streaming responses do not reliably expose a final usage
    # object. Mark the call unavailable rather than manufacturing token counts.
    if usage_tracker is not None:
        usage_tracker.record_unavailable(model)

    parts: list[str] = []
    for chunk in response:
        # Role-only and terminal frames legitimately omit content. A broken
        # envelope or a present non-text content field is different: skipping
        # it could turn a truncated stream into a successful research report.
        try:
            choice = chunk["choices"][0]
            content = choice["delta"].get("content", "")
        except (KeyError, IndexError, AttributeError, TypeError) as exc:
            raise ValueError("provider stream chunk missing a valid delta") from exc

        if not isinstance(content, str):
            raise ValueError("provider stream delta content must be text")
        _validate_finish_reason(choice, source="stream")
        if not content:
            continue

        parts.append(content)
        if websocket is not None:
            if hasattr(websocket, "send_text"):
                await websocket.send_text(content)
            elif hasattr(websocket, "send_json"):
                await websocket.send_json({"type": "report", "output": content})

    return "".join(parts)


def create_chat_completion(
    *,
    model: str,
    messages: Iterable[dict],
    stream: bool = False,
    websocket: Any = None,
    temperature: float | None = None,
    usage_tracker: UsageTracker | None = None,
    request_timeout_seconds: float | None = None,
):
    """Create a chat completion using the repository's pinned OpenAI client."""
    # Reject invalid tracked model identities before preparing messages or
    # invoking a paid provider. Late rejection by UsageTracker would discard
    # a completed response and leave its attempted consumption unmeasured.
    if usage_tracker is not None:
        UsageTracker._require_model_label(model)

    # Resolve and validate local request parameters before consuming a one-pass
    # input producer or entering the provider-attempt accounting boundary.
    # NaN compares neither <= nor >, so a sign-only timeout check is unsafe.
    resolved_temperature = CFG.temperature if temperature is None else temperature
    if type(resolved_temperature) not in (int, float):
        raise ValueError("temperature must be a finite number between 0 and 2")
    try:
        temperature_check = float(resolved_temperature)
    except (OverflowError, ValueError, TypeError) as exc:
        raise ValueError("temperature must be a finite number between 0 and 2") from exc
    if not math.isfinite(temperature_check) or not 0 <= temperature_check <= 2:
        raise ValueError("temperature must be a finite number between 0 and 2")

    if type(request_timeout_seconds) is bool:
        raise ValueError("request_timeout_seconds must be finite and positive")
    try:
        resolved_timeout = (
            float(OPENAI_REQUEST_TIMEOUT_SECONDS)
            if request_timeout_seconds is None
            else float(request_timeout_seconds)
        )
    except (OverflowError, ValueError, TypeError) as exc:
        raise ValueError("request_timeout_seconds must be finite and positive") from exc
    if not math.isfinite(resolved_timeout) or resolved_timeout <= 0:
        raise ValueError("request_timeout_seconds must be finite and positive")

    if stream:
        return _stream_completion(
            model=model,
            messages=messages,
            websocket=websocket,
            temperature=resolved_temperature,
            usage_tracker=usage_tracker,
            request_timeout_seconds=resolved_timeout,
        )

    # Materialization failures are local preparation errors, not attempts to
    # invoke the provider; do not inflate the prospective model-call ledger.
    prepared_messages = list(messages)
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=prepared_messages,
            temperature=resolved_temperature,
            request_timeout=resolved_timeout,
        )
    except Exception:
        # A failed provider invocation is still an attempted model call.
        # Preserve missing-usage exposure instead of silently dropping it.
        if usage_tracker is not None:
            usage_tracker.record_unavailable(model)
        raise
    if usage_tracker is not None:
        usage_tracker.record_response(model, response)
    return _choice_content(response)
