"""Independent, offline prepublication pilot-summary source-integrity tests.

Only synthetic traces and frozen prices; never contacts providers or reruns runs.
"""

import json
from pathlib import Path

import pytest

from scripts import summarize_pilot as pilot


PRICES = {"models": {"smart": {"input": 1.0, "output": 2.0}}}


def _trace():
    return {
        "variant_id": "D6",
        "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot",
        "run_id": "run-01",
        "completed": True,
        "source_count": 6,
        "successful_source_count": 5,
        "failed_source_count": 1,
        "search_call_count": 1,
        "model_call_count": 2,
        "prompt_tokens": 4,
        "completion_tokens": 3,
        "total_tokens": 7,
        "report_words": 12,
        "verified_claim_count": 0,
        "claim_support_rate": 0.0,
        "latency_seconds": 2.5,
        "provider_usage_by_model": {
            "smart": {"prompt_tokens": 4, "completion_tokens": 3}
        },
    }


def _write(tmp_path, trace, *, raw=None):
    folder = tmp_path / "traces" / "D6"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "run-01.json"
    payload = {"trace": trace, "experiment": {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot"
    }}
    path.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return path


def _rows(tmp_path, monkeypatch, trace, *, raw=None):
    _write(tmp_path, trace, raw=raw)
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path / "traces")
    return pilot._load_traces(PRICES)


def test_valid_trace_retains_cost_and_operational_values(tmp_path, monkeypatch):
    rows = _rows(tmp_path, monkeypatch, _trace())
    assert len(rows) == 1
    row = rows[0]
    assert row["source_count"] == 6
    assert row["total_tokens"] == 7
    assert row["completed"] is True
    assert row["latency_seconds"] == 2.5
    assert row["claim_support_rate"] == 0.0
    assert row["estimated_cost_usd"] == pytest.approx(10 / 1_000_000)
    assert row["cost_accounting_status"] == "estimated_from_frozen_uncached_rates"


@pytest.mark.parametrize("field,value", [
    ("source_count", "6"),
    ("successful_source_count", 5.9),
    ("failed_source_count", -1),
    ("search_call_count", True),
    ("model_call_count", None),
    ("report_words", "12"),
    ("verified_claim_count", False),
    ("supported_claim_count", -1),
    ("partially_supported_claim_count", 0.5),
    ("unsupported_claim_count", []),
    ("contradicted_claim_count", {}),
])
def test_summarizer_rejects_coerced_operational_counters(
    tmp_path, monkeypatch, field, value
):
    trace = _trace()
    trace[field] = value
    with pytest.raises(ValueError, match=f"pilot trace {field} must be a nonnegative integer"):
        _rows(tmp_path, monkeypatch, trace)


@pytest.mark.parametrize("field,value", [
    ("latency_seconds", -0.1),
    ("latency_seconds", "2.5"),
    ("latency_seconds", False),
    ("claim_support_rate", 1.1),
    ("claim_support_rate", -0.1),
    ("claim_support_rate", "0.5"),
])
def test_summarizer_rejects_nonfinite_or_out_of_domain_measures(
    tmp_path, monkeypatch, field, value
):
    trace = _trace()
    trace[field] = value
    with pytest.raises(ValueError, match=f"pilot trace {field} must be finite"):
        _rows(tmp_path, monkeypatch, trace)


@pytest.mark.parametrize("value", [1, 0, "true", None])
def test_summarizer_rejects_coerced_completion(tmp_path, monkeypatch, value):
    trace = _trace()
    trace["completed"] = value
    with pytest.raises(ValueError, match="pilot trace completed must be a boolean"):
        _rows(tmp_path, monkeypatch, trace)


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity", "1e309", "-1e309"])
def test_summarizer_rejects_nonfinite_json_even_in_unused_fields(
    tmp_path, monkeypatch, literal
):
    trace = _trace()
    raw = json.dumps({"trace": trace, "experiment": {
        "variant_id": "D6", "task_id": "pilot-01",
        "task_set_id": "synthetic-pilot"
    }})
    raw = '{"extra": ' + literal + ', ' + raw[1:]
    with pytest.raises(ValueError, match="unreadable or malformed pilot trace"):
        _rows(tmp_path, monkeypatch, trace, raw=raw)


def test_summarizer_rejects_last_key_wins_variant_attack(tmp_path, monkeypatch):
    trace = _trace()
    raw = json.dumps({"trace": trace, "experiment": {"variant_id": "D6"}})
    raw = raw.replace('"variant_id": "D6"', '"variant_id": "P6V", "variant_id": "D6"', 1)
    with pytest.raises(ValueError, match="unreadable or malformed pilot trace"):
        _rows(tmp_path, monkeypatch, trace, raw=raw)


def test_summarizer_rejects_duplicate_frozen_pricing_keys(tmp_path, monkeypatch):
    p = tmp_path / "frozen-pricing.json"
    p.write_text(
        '{"unit": "per_1m_text_tokens", "models": {"smart": '
        '{"input": 0.01, "input": 1.0, "output": 2.0}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(pilot, "PRICING_FILE", p)
    with pytest.raises(ValueError, match="invalid frozen pricing document"):
        pilot._load_pricing()


def test_summarizer_rejects_nonfinite_frozen_pricing_extra(tmp_path, monkeypatch):
    p = tmp_path / "frozen-pricing.json"
    p.write_text(
        '{"unit": "per_1m_text_tokens", "models": {}, "unused": 1e309}',
        encoding="utf-8",
    )
    monkeypatch.setattr(pilot, "PRICING_FILE", p)
    with pytest.raises(ValueError, match="invalid frozen pricing document"):
        pilot._load_pricing()


def test_malformed_inputs_leave_both_summary_destinations_unwritten(tmp_path, monkeypatch):
    trace = _trace()
    trace["source_count"] = "6"
    _write(tmp_path, trace)
    monkeypatch.setattr(pilot, "TRACE_ROOT", tmp_path / "traces")
    monkeypatch.setattr(pilot, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "PRICING_FILE", tmp_path / "pricing.json")
    canonical = Path(__file__).resolve().parents[1] / "experiments" / "openai_pricing_2026-09-08.json"
    pilot.PRICING_FILE.write_bytes(canonical.read_bytes())
    monkeypatch.setattr(pilot, "OUTPUT_JSON", tmp_path / "pilot_summary.json")
    monkeypatch.setattr(pilot, "OUTPUT_CSV", tmp_path / "pilot_runs.csv")
    with pytest.raises(ValueError, match="pilot trace source_count must be a nonnegative integer"):
        pilot.main()
    assert not pilot.OUTPUT_JSON.exists()
    assert not pilot.OUTPUT_CSV.exists()
