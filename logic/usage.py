"""Provider-independent token-usage accounting for experiment traces."""

from __future__ import annotations

from threading import Lock
from typing import Any


class UsageTracker:
    """Thread-safe accumulator for provider-reported model usage.

    Source summarization can run in a thread pool, so recording must be safe
    across concurrent completions. Missing or invalid provider token usage is
    never estimated; such calls are counted separately as unavailable.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._model_calls = 0
        self._unavailable_calls = 0
        self._by_model: dict[str, dict[str, int]] = {}

    @staticmethod
    def _usage_value(usage: Any, key: str) -> int | None:
        """Distinguish a reported zero from missing or malformed token counts."""
        try:
            try:
                value = usage.get(key, None)
            except AttributeError:
                value = getattr(usage, key, None)
        except Exception:
            # Provider-controlled metadata must not fail an otherwise
            # completed experiment run. Preserve missingness, not zeros.
            return None
        return value if type(value) is int and value >= 0 else None

    @staticmethod
    def _require_model_label(model: str) -> None:
        """Reject keys that cannot be faithfully represented in usage ledgers.

        A non-string (or a string subclass with nonstandard hashing) can make
        per-model insertion fail after global counters have already advanced.
        Preserve exact valid string labels, including legacy empty labels.
        """
        if type(model) is not str:
            raise ValueError("model must be an exact string")

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
        self._require_model_label(model)
        try:
            try:
                usage = response.get("usage")
            except AttributeError:
                usage = getattr(response, "usage", None)
        except Exception:
            # A response was obtained, but its usage metadata is unreadable.
            # Measurement faults must not discard a completed provider output.
            self.record_unavailable(model)
            return

        if usage is None:
            self.record_unavailable(model)
            return

        prompt_tokens = self._usage_value(usage, "prompt_tokens")
        completion_tokens = self._usage_value(usage, "completion_tokens")
        # Both category counts are necessary for per-model cost attribution.
        # Treat an incomplete or malformed record as unavailable, never zero.
        if prompt_tokens is None or completion_tokens is None:
            self.record_unavailable(model)
            return
        # Legacy providers may omit the total, but a *present* total must be
        # an exact, nonnegative integer matching the category sum.
        missing = object()
        try:
            try:
                reported_total = usage.get("total_tokens", missing)
            except AttributeError:
                reported_total = getattr(usage, "total_tokens", missing)
        except Exception:
            # An unreadable *present-or-absent* total is not equivalent to
            # the legitimately omitted legacy total_tokens field.
            self.record_unavailable(model)
            return
        expected_total = prompt_tokens + completion_tokens
        if reported_total is not missing and (
            type(reported_total) is not int or reported_total != expected_total
        ):
            self.record_unavailable(model)
            return

        with self._lock:
            self._model_calls += 1
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            bucket = self._model_bucket(model)
            bucket["model_calls"] += 1
            bucket["prompt_tokens"] += prompt_tokens
            bucket["completion_tokens"] += completion_tokens
            bucket["total_tokens"] += expected_total

    def record_unavailable(self, model: str) -> None:
        self._require_model_label(model)
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


# Keep response identity separate from the requested-model cost ledger. Only
# the single-call evaluator opts in; treatment and streaming snapshots remain
# unchanged. These are provider-reported labels, not authenticated identities.
_RESPONSE_IDENTITY_FIELDS = ("model", "id", "system_fingerprint")
_MAX_RESPONSE_IDENTITY_BYTES = 1024


def _valid_response_identity_value(value: Any) -> bool:
    if type(value) is not str or not value or len(value) > _MAX_RESPONSE_IDENTITY_BYTES:
        return False
    try:
        return value.isprintable() and bool(value.strip()) and (
            len(value.encode("utf-8")) <= _MAX_RESPONSE_IDENTITY_BYTES
        )
    except UnicodeError:
        return False


def _capture_response_identity(response: Any) -> dict:
    fields = {}
    for name in _RESPONSE_IDENTITY_FIELDS:
        try:
            try:
                value = response.get(name, None)
            except AttributeError:
                value = getattr(response, name, None)
        except Exception:
            fields[name] = {"status": "invalid", "value": None}
            continue
        if value is None:
            fields[name] = {"status": "unavailable", "value": None}
        elif _valid_response_identity_value(value):
            fields[name] = {"status": "reported", "value": value}
        else:
            fields[name] = {"status": "invalid", "value": None}
    return fields


def validate_response_identity(receipt: Any) -> None:
    """Check the optional provider metadata receipt without inferring identity."""
    if type(receipt) is not dict or set(receipt) != set(_RESPONSE_IDENTITY_FIELDS):
        raise ValueError("provider_response_identity has invalid fields")
    for entry in receipt.values():
        if type(entry) is not dict or set(entry) != {"status", "value"}:
            raise ValueError("provider_response_identity has invalid entry")
        status, value = entry["status"], entry["value"]
        if status == "reported" and _valid_response_identity_value(value):
            continue
        if status in ("unavailable", "invalid") and value is None:
            continue
        raise ValueError("provider_response_identity has invalid status/value")


class EvaluatorResponseUsageTracker(UsageTracker):
    """Opt-in metadata capture for the evaluator's one non-streaming call.

    The ordinary token ledger still uses the requested model and frozen
    pricing. Multiple responses cannot be represented as one receipt.
    """

    def __init__(self) -> None:
        super().__init__()
        self._response_identity: dict | None = None
        self._response_identity_count = 0

    def record_response(self, model: str, response: Any) -> None:
        super().record_response(model, response)
        identity = _capture_response_identity(response)
        with self._lock:
            self._response_identity_count += 1
            self._response_identity = (
                identity if self._response_identity_count == 1 else None
            )

    def snapshot_response_identity(self) -> dict:
        with self._lock:
            if self._model_calls != 1 or self._response_identity is None:
                raise ValueError("provider_response_identity requires exactly one response")
            return {name: dict(entry) for name, entry in self._response_identity.items()}
