"""Offline, synthetic diagnostic-pilot usage/cost integrity regression tests.

No treatment, provider, evaluator, or human annotation is executed.
"""

import json
import math

import pytest

from scripts import summarize_pilot as pilot


PRICING = {"models": {"smart": {"input": 2.0, "output": 12.0}}}
VALID_USAGE = {"smart": {"prompt_tokens": 4, "completion_tokens": 2}}


def test_valid_frozen_rate_and_usage_preserve_estimate():
    cost, status = pilot._estimate_reported_token_cost(VALID_USAGE, PRICING)
    assert status == "estimated_from_frozen_uncached_rates"
    assert cost == pytest.approx(32 / 1_000_000)


def test_missing_usage_map_is_explicitly_uncosted():
    assert pilot._estimate_reported_token_cost(None, PRICING) == (
        None, "missing_usage_by_model"
    )
    assert pilot._estimate_reported_token_cost({}, PRICING) == (
        None, "no_reported_tokens"
    )


def test_unknown_price_remains_explicitly_uncosted():
    assert pilot._estimate_reported_token_cost(
        {"other": {"prompt_tokens": 1, "completion_tokens": 1}}, PRICING
    ) == (None, "unknown_model_price:other")


@pytest.mark.parametrize("value", [-1, 1.5, True, False, "3", None, float("nan")])
def test_invalid_prompt_token_counts_rejected(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        pilot._estimate_reported_token_cost(
            {"smart": {"prompt_tokens": value, "completion_tokens": 2}},
            PRICING,
        )


@pytest.mark.parametrize("value", [-1, 2.1, True, "2", None, float("inf")])
def test_invalid_completion_token_counts_rejected(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        pilot._estimate_reported_token_cost(
            {"smart": {"prompt_tokens": 4, "completion_tokens": value}},
            PRICING,
        )


@pytest.mark.parametrize("field,value", [
    ("input", -1), ("input", float("nan")), ("input", float("inf")),
    ("input", True), ("input", "2.0"), ("output", -0.1),
    ("output", float("-inf")), ("output", None), ("output", False),
])
def test_invalid_frozen_price_rejected(field, value):
    prices = {"models": {"smart": {"input": 2.0, "output": 12.0}}}
    prices["models"]["smart"][field] = value
    with pytest.raises(ValueError, match="finite and nonnegative"):
        pilot._estimate_reported_token_cost(VALID_USAGE, prices)


@pytest.mark.parametrize("usage", [None, "not-a-model-bucket", [], 1])
def test_malformed_model_bucket_is_not_silently_dropped(usage):
    with pytest.raises(ValueError, match="invalid provider usage model bucket"):
        pilot._estimate_reported_token_cost({"smart": usage}, PRICING)


def _write_trace(root, trace):
    folder = root / "D6"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "r1.json").write_text(json.dumps({
        "trace": trace,
        "experiment": {
            "variant_id": "D6", "task_id": "pilot-01",
            "task_set_id": "synthetic-pilot",
        },
    }), encoding="utf-8")


def _trace():
    return {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot", "run_id": "r1",
        "provider_usage_by_model": VALID_USAGE,
        "prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6,
        "completed": True,
    }


def test_matching_model_ledger_is_costed(tmp_path, monkeypatch):
    _write_trace(tmp_path, _trace())
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path)
    rows = pilot._load_traces(PRICING)
    assert len(rows) == 1
    assert rows[0]["total_tokens"] == 6
    assert rows[0]["cost_accounting_status"] == "estimated_from_frozen_uncached_rates"
    assert rows[0]["estimated_cost_usd"] == pytest.approx(32 / 1_000_000)


@pytest.mark.parametrize("field,replacement", [
    ("prompt_tokens", 5), ("completion_tokens", 3),
    ("total_tokens", 7), ("total_tokens", "6"), ("prompt_tokens", True),
])
def test_mismatched_model_ledger_fails_before_summary(tmp_path, monkeypatch, field, replacement):
    trace = _trace()
    trace[field] = replacement
    _write_trace(tmp_path, trace)
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path)
    with pytest.raises(ValueError, match="provider usage ledger mismatch"):
        pilot._load_traces(PRICING)


def test_multi_model_ledger_uses_sum_not_one_bucket():
    trace = {
        "prompt_tokens": 6, "completion_tokens": 9, "total_tokens": 15,
    }
    by_model = {
        "a": {"prompt_tokens": 4, "completion_tokens": 2},
        "b": {"prompt_tokens": 2, "completion_tokens": 7},
    }
    pilot._verify_provider_usage_ledger(trace, by_model)


def test_legacy_absent_ledger_remains_uncosted_not_imputed():
    pilot._verify_provider_usage_ledger({"total_tokens": 100}, {})
    assert pilot._estimate_reported_token_cost({}, PRICING) == (
        None, "no_reported_tokens"
    )


def test_invalid_model_bucket_fails_even_if_another_model_unpriced():
    with pytest.raises(ValueError, match="invalid provider usage model bucket"):
        pilot._verify_provider_usage_ledger(
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            {"unpriced": {"prompt_tokens": 0, "completion_tokens": 0}, "bad": []},
        )
