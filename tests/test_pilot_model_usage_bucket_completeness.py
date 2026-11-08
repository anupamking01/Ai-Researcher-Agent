"""Synthetic, offline diagnostic-pilot model-usage completeness tests.

No live providers, treatment runs, evaluators or human ratings.
"""
import json
from pathlib import Path

import pytest

from scripts import summarize_pilot as pilot

PRICES = {"models": {"smart": {"input": 1.0, "output": 2.0}}}
COMPLETE_USAGE = {"prompt_tokens": 3, "completion_tokens": 2}


def _trace():
    return {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-usage", "run_id": "r1",
        "completed": True, "prompt_tokens": 3, "completion_tokens": 2,
        "total_tokens": 5,
        "provider_usage_by_model": {"smart": dict(COMPLETE_USAGE)},
    }


def _write_trace(tmp_path, trace):
    root = tmp_path / "traces"
    folder = root / "D6"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "r1.json").write_text(
        json.dumps({"trace": trace, "experiment": {
            "variant_id": "D6", "task_id": "pilot-01",
            "task_set_id": "synthetic-usage",
        }}), encoding="utf-8",
    )
    return root


def _load(tmp_path, monkeypatch, trace):
    monkeypatch.setattr(pilot, "TRACE_ROOT", _write_trace(tmp_path, trace))
    return pilot._load_traces(PRICES)


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_missing_model_token_rejected_by_cost_calculator(field):
    usage = dict(COMPLETE_USAGE)
    del usage[field]
    with pytest.raises(ValueError, match=f"smart.*{field}.*nonnegative integer"):
        pilot._estimate_reported_token_cost({"smart": usage}, PRICES)


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_missing_model_token_rejected_by_independent_ledger(field):
    usage = dict(COMPLETE_USAGE)
    del usage[field]
    with pytest.raises(ValueError, match=f"smart.*{field}.*nonnegative integer"):
        pilot._verify_provider_usage_ledger(_trace(), {"smart": usage})


@pytest.mark.parametrize("field", ["prompt_tokens", "completion_tokens"])
def test_missing_model_token_rejected_before_summary(tmp_path, monkeypatch, field):
    trace = _trace()
    del trace["provider_usage_by_model"]["smart"][field]
    with pytest.raises(ValueError, match=f"smart.*{field}.*nonnegative integer"):
        _load(tmp_path, monkeypatch, trace)


@pytest.mark.parametrize("bad_map", [None, [], ["smart"], "unknown", 7, True, 0.0])
def test_present_malformed_map_cannot_be_mislabeled_missing(
    tmp_path, monkeypatch, bad_map
):
    trace = _trace()
    trace["provider_usage_by_model"] = bad_map
    with pytest.raises(ValueError, match="provider_usage_by_model must be a mapping"):
        _load(tmp_path, monkeypatch, trace)


def test_absent_legacy_map_remains_explicitly_uncosted(tmp_path, monkeypatch):
    trace = _trace()
    del trace["provider_usage_by_model"]
    rows = _load(tmp_path, monkeypatch, trace)
    assert rows[0]["estimated_cost_usd"] is None
    assert rows[0]["cost_accounting_status"] == "no_reported_tokens"


def test_explicit_zero_token_categories_remain_valid(tmp_path, monkeypatch):
    trace = _trace()
    trace["provider_usage_by_model"] = {
        "smart": {"prompt_tokens": 0, "completion_tokens": 0}
    }
    trace.update(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    rows = _load(tmp_path, monkeypatch, trace)
    assert rows[0]["estimated_cost_usd"] is None
    assert rows[0]["cost_accounting_status"] == "no_reported_tokens"


def test_complete_usage_retains_existing_cost(tmp_path, monkeypatch):
    rows = _load(tmp_path, monkeypatch, _trace())
    assert rows[0]["estimated_cost_usd"] == pytest.approx(7 / 1_000_000)
    assert rows[0]["cost_accounting_status"] == "estimated_from_frozen_uncached_rates"


def test_incomplete_ledger_cannot_publish_summary_or_csv(tmp_path, monkeypatch):
    trace = _trace()
    del trace["provider_usage_by_model"]["smart"]["completion_tokens"]
    monkeypatch.setattr(pilot, "TRACE_ROOT", _write_trace(tmp_path, trace))
    monkeypatch.setattr(pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "PRICING_FILE", tmp_path / "pricing.json")
    pinned = Path(__file__).resolve().parents[1] / "experiments" / "openai_pricing_2026-09-08.json"
    pilot.PRICING_FILE.write_bytes(pinned.read_bytes())
    monkeypatch.setattr(pilot, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(pilot, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    with pytest.raises(ValueError, match="smart.*completion_tokens.*nonnegative integer"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
