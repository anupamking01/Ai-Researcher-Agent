"""Provider-independent token-usage accounting for experiment traces."""

from __future__ import annotations

from threading import Lock
from typing import Any


class UsageTracker:
    """Thread-safe accumulator for provider-reported model usage.

    Source summarization can run in a thread pool, so recording must be safe
    across concurrent completions. Missing provider usage is never estimated;
    such calls are counted separately as unavailable.
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
