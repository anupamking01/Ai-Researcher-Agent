"""Synthetic offline parity tests for published diagnostic-pilot pair deltas.

No live treatments, evaluators, frozen analysis, or human ratings are run.
"""
import json

import pytest

from scripts.validate_pilot_artifacts import validate_pilot


ARMS = ("D6", "P6", "P6V")
TASKS = ("pilot-01", "pilot-02")
FACTOR = {
    "D6": ("direct", "none"),
    "P6": ("planner", "none"),
    "P6V": ("planner", "verify"),
}
# Per-cell (total tokens, model calls, successful URLs, seconds).
OBSERVED = {
    ("D6", "pilot-01"): (100, 2, 6, 3.0),
    ("D6", "pilot-02"): (140, 3, 5, 4.0),
    ("P6", "pilot-01"): (130, 3, 6, 4.0),
    ("P6", "pilot-02"): (160, 4, 5, 7.0),
    ("P6V", "pilot-01"): (120, 5, 6, 8.0),
    ("P6V", "pilot-02"): (200, 6, 6, 9.0),
}


def _write(root, selected=ARMS):
    manifest = {
        "schema_version": 1,
        "task_set_id": "synthetic-pairs",
        "variants": list(selected), "task_ids": list(TASKS),
        "smart_model": "smart", "fast_model": "fast",
        "temperature": 1.0, "started_at_utc": "2026-09-07T23:59:59+00:00",
    }
    cells = [(arm, task) for arm in selected for task in TASKS]
    progress = {
        "schema_version": 1,
        "task_set_id": "synthetic-pairs",
        "variants": list(selected), "task_ids": list(TASKS),
        "total_expected_runs": len(cells), "attempted_runs": len(cells),
        "completed_runs": len(cells), "failed_runs": 0, "timeout_runs": 0,
        "current": None, "started_at_utc": "2026-09-08T00:00:00+00:00",
        "finished_at_utc": "2026-09-08T00:09:00+00:00",
        "events": [],
    }
    for index, (arm, task) in enumerate(cells):
        progress["events"].append({
            "variant": arm, "task_id": task, "status": "completed",
            "started_at_utc": f"2026-09-08T00:0{index}:00+00:00",
            "finished_at_utc": f"2026-09-08T00:0{index}:30+00:00",
        })
        tokens, calls, successes, seconds = OBSERVED[(arm, task)]
        planning_mode, verification_mode = FACTOR[arm]
        urls = [f"https://example.invalid/{arm}/{task}/{j}" for j in range(6)]
        target = root / "experiment_traces" / arm
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{arm}-{task}.json").write_text(json.dumps({
            "schema_version": 2,
            "experiment": {"variant_id": arm, "task_id": task,
                           "task_set_id": "synthetic-pairs"},
            "trace": {
                "variant_id": arm, "task_id": task,
                "task_set_id": "synthetic-pairs",
                "run_id": f"{arm}-{task}",
                "planning_mode": planning_mode, "verification_mode": verification_mode,
                "source_budget": 6, "source_count": 6,
                "successful_source_count": successes,
                "failed_source_count": 6 - successes,
                "scheduled_urls": urls, "successful_urls": urls[:successes],
                "failed_urls": urls[successes:],
                "query_count": 1 if arm == "D6" else 4,
                "search_call_count": 1 if arm == "D6" else 4,
                "completed": True, "research_context_words": 20,
                "report_words": 30, "model_call_count": calls,
                "total_tokens": tokens, "prompt_tokens": tokens - 20,
                "completion_tokens": 20,
                "provider_usage_by_model": {
                    "smart": {"prompt_tokens": tokens - 20, "completion_tokens": 20},
                },
                "usage_accounting_status": "provider_usage_complete",
                "smart_model": "smart", "fast_model": "fast",
                "temperature": 1.0, "latency_seconds": seconds,
                "verification_status": "ok" if arm == "P6V" else "not_requested",
                "verified_claim_count": 2 if arm == "P6V" else 0,
            },
        }), encoding="utf-8")
    comparisons = {}
    for left, right, name in (
        ("D6", "P6", "P6_minus_D6"), ("P6", "P6V", "P6V_minus_P6")
    ):
        union = list(TASKS) if left in selected or right in selected else []
        shared = list(TASKS) if left in selected and right in selected else []
        pairs = []
        for task in shared:
            before, after = OBSERVED[(left, task)], OBSERVED[(right, task)]
            pairs.append({
                "task_id": task,
                "total_tokens_delta": after[0] - before[0],
                "model_calls_delta": after[1] - before[1],
                "successful_sources_delta": after[2] - before[2],
                "latency_seconds_delta": after[3] - before[3],
                "estimated_cost_usd_delta": None,
            })
        def mean(key):
            return sum(row[key] for row in pairs) / len(pairs) if pairs else None
        comparisons[name] = {
            "n_tasks_union": len(union), "n_pairs": len(shared),
            "n_costed_pairs": 0, "n_uncosted_pairs": len(shared),
            "missing_left_task_ids": union if left not in selected else [],
            "missing_right_task_ids": union if right not in selected else [],
            "pairs": pairs,
            "avg_total_tokens_delta": mean("total_tokens_delta"),
            "avg_latency_seconds_delta": mean("latency_seconds_delta"),
            "avg_model_calls_delta": mean("model_calls_delta"),
            "avg_successful_sources_delta": mean("successful_sources_delta"),
        }
    summary = {
        "schema_version": 1, "n_trace_files": len(cells),
        "variant_summary": {
            arm: {"n_runs": len(TASKS), "n_completed": len(TASKS)}
            for arm in selected
        },
        "paired_operational_differences": comparisons,
    }
    for name, payload in (
        ("pilot_manifest.json", manifest),
        ("pilot_progress.json", progress),
        ("pilot_summary.json", summary),
    ):
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    return summary


def _save(root, data):
    (root / "pilot_summary.json").write_text(json.dumps(data), encoding="utf-8")


def _errors(root):
    return " | ".join(validate_pilot(root))


@pytest.mark.parametrize("arms", [ARMS, ("D6", "P6"), ("D6",)])
def test_published_pairs_match_all_selected_source_cells(tmp_path, arms):
    _write(tmp_path, arms)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("field", [
    "total_tokens_delta", "latency_seconds_delta", "model_calls_delta",
    "successful_sources_delta",
])
def test_falsified_paired_row_fails_even_if_counts_still_match(tmp_path, field):
    data = _write(tmp_path)
    data["paired_operational_differences"]["P6_minus_D6"]["pairs"][0][field] += 1
    _save(tmp_path, data)
    assert field in _errors(tmp_path)


@pytest.mark.parametrize("field", [
    "avg_total_tokens_delta", "avg_latency_seconds_delta",
    "avg_model_calls_delta", "avg_successful_sources_delta",
])
def test_falsified_pair_mean_fails_even_if_rows_are_correct(tmp_path, field):
    data = _write(tmp_path)
    data["paired_operational_differences"]["P6V_minus_P6"][field] += 1
    _save(tmp_path, data)
    assert field in _errors(tmp_path)


@pytest.mark.parametrize("field", ["n_pairs", "n_tasks_union"])
def test_paired_denominator_cannot_disagree_with_selected_tasks(tmp_path, field):
    data = _write(tmp_path)
    data["paired_operational_differences"]["P6_minus_D6"][field] += 1
    _save(tmp_path, data)
    assert field in _errors(tmp_path)


@pytest.mark.parametrize("change", ["drop", "duplicate", "reorder", "wrong_task"])
def test_paired_task_rows_cannot_be_omitted_or_misidentified(tmp_path, change):
    data = _write(tmp_path)
    pairs = data["paired_operational_differences"]["P6_minus_D6"]["pairs"]
    if change == "drop":
        pairs.pop()
    if change == "duplicate":
        pairs[1] = dict(pairs[0])
    if change == "reorder":
        pairs.reverse()
    if change == "wrong_task":
        pairs[0]["task_id"] = "not-a-selected-task"
    _save(tmp_path, data)
    assert ".pairs" in _errors(tmp_path)


@pytest.mark.parametrize("bad", [None, [], {}, {"P6_minus_D6": {}}])
def test_missing_or_unselected_comparison_set_fails(tmp_path, bad):
    data = _write(tmp_path)
    data["paired_operational_differences"] = bad
    _save(tmp_path, data)
    assert "paired_operational_differences" in _errors(tmp_path)


@pytest.mark.parametrize("bad", [None, True, 1.0, "1", 2])
def test_invalid_summary_version_rejected(tmp_path, bad):
    data = _write(tmp_path)
    data["schema_version"] = bad
    _save(tmp_path, data)
    assert "summary.schema_version" in _errors(tmp_path)


def test_versioned_summary_must_contain_paired_comparisons(tmp_path):
    data = _write(tmp_path)
    data.pop("paired_operational_differences")
    _save(tmp_path, data)
    assert "missing paired operational comparisons" in _errors(tmp_path)


def test_source_mutation_cannot_leave_stale_summary_passing(tmp_path):
    _write(tmp_path)
    target = tmp_path / "experiment_traces" / "P6" / "P6-pilot-01.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    trace = data["trace"]
    trace["total_tokens"] += 10
    trace["prompt_tokens"] += 10
    trace["provider_usage_by_model"]["smart"]["prompt_tokens"] += 10
    target.write_text(json.dumps(data), encoding="utf-8")
    assert "total_tokens_delta" in _errors(tmp_path)


@pytest.mark.parametrize("bad", [True, "30", None, 30.5, 10**400])
def test_malformed_paired_token_value_rejected(tmp_path, bad):
    data = _write(tmp_path)
    data["paired_operational_differences"]["P6_minus_D6"]["pairs"][0]["total_tokens_delta"] = bad
    _save(tmp_path, data)
    assert "total_tokens_delta" in _errors(tmp_path)


def test_unversioned_legacy_summary_can_be_audited_if_pairs_are_supplied(tmp_path):
    data = _write(tmp_path)
    data.pop("schema_version")
    _save(tmp_path, data)
    assert validate_pilot(tmp_path) == []
    data["paired_operational_differences"]["P6_minus_D6"]["pairs"][0]["total_tokens_delta"] = 999
    _save(tmp_path, data)
    assert "total_tokens_delta" in _errors(tmp_path)


# Version 2 independently verifies cost and missingness against selected traces
# and a local synthetic frozen-pricing fixture, never a provider or past run.
from scripts import summarize_pilot as pilot_producer
from scripts import validate_pilot_artifacts as pilot_validator


def _v2_cost_fixture(root, monkeypatch, unpriced=None):
    summary = _write(root)
    pricing_file = root / "synthetic_frozen_pricing.json"
    pricing_file.write_text(json.dumps({
        "unit": "per_1m_text_tokens", "effective_date": "2026-09-08",
        "currency": "USD",
        "models": {"smart": {"input": 2.0, "output": 12.0}},
    }), encoding="utf-8")
    monkeypatch.setattr(pilot_validator, "PILOT_PRICING_FILE", pricing_file)
    summary["schema_version"] = 2
    summary["pricing_reference"] = {
        "file": "experiments/openai_pricing_2026-09-08.json",
        "effective_date": "2026-09-08", "currency": "USD",
        "method": "provider-reported prompt/output tokens multiplied by frozen uncached text-token rates",
    }
    rows = []
    for arm in ARMS:
        for task in TASKS:
            tokens, calls, successes, seconds = OBSERVED[(arm, task)]
            missing = unpriced == (arm, task)
            cost = None if missing else ((tokens - 20) * 2.0 + 20 * 12.0) / 1_000_000
            status = ("unknown_model_price:unknown" if missing
                      else "estimated_from_frozen_uncached_rates")
            if missing:
                source = root / "experiment_traces" / arm / f"{arm}-{task}.json"
                payload = json.loads(source.read_text(encoding="utf-8"))
                payload["trace"]["provider_usage_by_model"]["unknown"] = (
                    payload["trace"]["provider_usage_by_model"].pop("smart")
                )
                source.write_text(json.dumps(payload), encoding="utf-8")
            rows.append({
                "variant_id": arm, "task_set_id": "synthetic-pairs",
                "task_id": task, "run_id": f"{arm}-{task}", "completed": True,
                "source_count": 6, "successful_source_count": successes,
                "failed_source_count": 6 - successes, "search_call_count": 4,
                "model_call_count": calls, "prompt_tokens": tokens - 20,
                "completion_tokens": 20, "total_tokens": tokens,
                "latency_seconds": seconds, "report_words": 30,
                "claims_checked": 0, "claim_support_rate": 0.0,
                "usage_accounting_status": "provider_usage_complete",
                "estimated_cost_usd": cost, "cost_accounting_status": status,
            })
    variants = pilot_producer._variant_summary(rows)
    for arm in ARMS:
        for field in (
            "costed_runs", "uncosted_runs", "uncosted_task_ids",
            "cost_accounting_status_counts", "avg_estimated_cost_usd",
        ):
            summary["variant_summary"][arm][field] = variants[arm][field]
    pairs = pilot_producer._paired_operational_differences(rows)
    for name in ("P6_minus_D6", "P6V_minus_P6"):
        target = summary["paired_operational_differences"][name]
        for field in (
            "n_costed_pairs", "n_uncosted_pairs", "costed_pair_task_ids",
            "uncosted_pair_details", "avg_estimated_cost_usd_delta",
        ):
            target[field] = pairs[name][field]
        for target_row, expected_row in zip(target["pairs"], pairs[name]["pairs"]):
            target_row["estimated_cost_usd_delta"] = expected_row["estimated_cost_usd_delta"]
    _save(root, summary)
    return summary


@pytest.mark.parametrize("unpriced", [None, ("P6", "pilot-02")])
def test_version2_cost_matches_traces_and_frozen_price(tmp_path, monkeypatch, unpriced):
    _v2_cost_fixture(tmp_path, monkeypatch, unpriced)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("field", [
    "n_costed_pairs", "n_uncosted_pairs", "costed_pair_task_ids",
    "uncosted_pair_details", "avg_estimated_cost_usd_delta",
])
def test_version2_rejects_falsified_paired_cost_coverage(tmp_path, monkeypatch, field):
    data = _v2_cost_fixture(tmp_path, monkeypatch, ("P6", "pilot-02"))
    record = data["paired_operational_differences"]["P6_minus_D6"]
    if field in ("n_costed_pairs", "n_uncosted_pairs"):
        record[field] += 1
    elif field == "avg_estimated_cost_usd_delta":
        record[field] += .01
    else:
        record[field] = []
    _save(tmp_path, data)
    assert field in _errors(tmp_path)


@pytest.mark.parametrize("field", [
    "costed_runs", "uncosted_runs", "uncosted_task_ids",
    "cost_accounting_status_counts", "avg_estimated_cost_usd",
])
def test_version2_rejects_falsified_arm_cost_coverage(tmp_path, monkeypatch, field):
    data = _v2_cost_fixture(tmp_path, monkeypatch, ("P6", "pilot-02"))
    arm = data["variant_summary"]["P6"]
    if field in ("costed_runs", "uncosted_runs"):
        arm[field] += 1
    elif field == "avg_estimated_cost_usd":
        arm[field] += .01
    else:
        arm[field] = {} if field == "cost_accounting_status_counts" else []
    _save(tmp_path, data)
    assert field in _errors(tmp_path)


@pytest.mark.parametrize("replacement", [0.0, None, True, "1", 1e30])
def test_version2_rejects_wrong_pair_cost_value(tmp_path, monkeypatch, replacement):
    data = _v2_cost_fixture(tmp_path, monkeypatch)
    data["paired_operational_differences"]["P6_minus_D6"]["pairs"][0][
        "estimated_cost_usd_delta"
    ] = replacement
    _save(tmp_path, data)
    assert "estimated_cost_usd_delta" in _errors(tmp_path)


def test_version2_source_token_change_invalidates_prior_cost(tmp_path, monkeypatch):
    _v2_cost_fixture(tmp_path, monkeypatch)
    source = tmp_path / "experiment_traces" / "P6" / "P6-pilot-01.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    trace = data["trace"]
    trace["prompt_tokens"] += 10
    trace["total_tokens"] += 10
    trace["provider_usage_by_model"]["smart"]["prompt_tokens"] += 10
    source.write_text(json.dumps(data), encoding="utf-8")
    assert "total_tokens_delta" in _errors(tmp_path)


def test_version2_bad_price_reference_fails(tmp_path, monkeypatch):
    data = _v2_cost_fixture(tmp_path, monkeypatch)
    data["pricing_reference"]["effective_date"] = "suspicious"
    _save(tmp_path, data)
    assert "pricing_reference" in _errors(tmp_path)


def test_version2_falsified_price_table_fails_without_repricing_outcomes(tmp_path, monkeypatch):
    data = _v2_cost_fixture(tmp_path, monkeypatch)
    pricing = pilot_validator.PILOT_PRICING_FILE
    altered = json.loads(pricing.read_text(encoding="utf-8"))
    altered["models"]["smart"]["output"] = 70.0
    pricing.write_text(json.dumps(altered), encoding="utf-8")
    assert "source cost" in _errors(tmp_path)


def test_version2_missing_cost_coverage_not_silently_accepted(tmp_path, monkeypatch):
    data = _v2_cost_fixture(tmp_path, monkeypatch)
    del data["paired_operational_differences"]["P6_minus_D6"]["costed_pair_task_ids"]
    _save(tmp_path, data)
    assert "costed_pair_task_ids" in _errors(tmp_path)
