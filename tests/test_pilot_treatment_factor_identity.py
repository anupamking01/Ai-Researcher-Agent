"""Synthetic, offline checks that pilot treatment labels bind their factors.

These tests do not run a model, browser, evaluator, or human annotation.
"""
import json

import pytest

from logic.experiment import ExperimentConfig
from scripts.validate_pilot_artifacts import validate_pilot


# Explicit expectations intentionally independent of the production validator.
FROZEN = {
    "D6": ("direct", 6, "none"),
    "P6": ("planner", 6, "none"),
    "P6V": ("planner", 6, "verify"),
}


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _make_cell(root, variant):
    planning, budget, verification = FROZEN[variant]
    task_set = "synthetic-pilot"
    task_id = "pilot-01"
    urls = [f"https://example.invalid/evidence/{index}" for index in range(budget)]
    manifest = {
        "task_set_id": task_set, "variants": [variant], "task_ids": [task_id],
        "smart_model": "synthetic-smart", "fast_model": "synthetic-fast",
        "temperature": 1.0,
    }
    progress = {
        "task_set_id": task_set, "variants": [variant], "task_ids": [task_id],
        "total_expected_runs": 1, "attempted_runs": 1, "completed_runs": 1,
        "failed_runs": 0, "timeout_runs": 0,
    }
    summary = {"n_trace_files": 1, "variant_summary": {
        variant: {"n_runs": 1, "n_completed": 1},
    }}
    experiment = {
        "variant_id": variant, "task_id": task_id, "task_set_id": task_set,
        "planning_mode": planning, "source_budget": budget,
        "verification_mode": verification,
    }
    trace = {
        "variant_id": variant, "task_id": task_id, "task_set_id": task_set,
        "completed": True, "planning_mode": planning,
        "source_budget": budget, "source_count": budget,
        "successful_source_count": budget, "failed_source_count": 0,
        "scheduled_urls": urls, "successful_urls": list(urls),
        "failed_urls": [], "query_count": 1 if planning == "direct" else 4,
        "search_call_count": 1 if planning == "direct" else 4,
        "research_context_words": 42, "report_words": 50,
        "model_call_count": 3, "total_tokens": 100,
        "usage_accounting_status": "provider_usage_complete",
        "smart_model": "synthetic-smart", "fast_model": "synthetic-fast",
        "temperature": 1.0, "verification_mode": verification,
        "verification_status": "ok" if verification == "verify" else "not_requested",
        "verified_claim_count": 2 if verification == "verify" else 0,
    }
    for name, payload in (
        ("pilot_manifest.json", manifest), ("pilot_progress.json", progress),
        ("pilot_summary.json", summary),
    ):
        _write_json(root / name, payload)
    trace_path = root / "experiment_traces" / variant / "run.json"
    _write_json(trace_path, {"experiment": experiment, "trace": trace})
    return trace_path, experiment, trace


def _save(path, experiment, trace):
    _write_json(path, {"experiment": experiment, "trace": trace})


@pytest.mark.parametrize("variant", ["D6", "P6", "P6V"])
def test_untampered_frozen_pilot_factor_assignments_pass(tmp_path, variant):
    _make_cell(tmp_path, variant)
    assert validate_pilot(tmp_path) == []


@pytest.mark.parametrize("variant", ["D6", "P6", "P6V"])
def test_producer_variant_factors_remain_consistent_with_independent_audit(variant):
    expected_planning, expected_budget, expected_verification = FROZEN[variant]
    config = ExperimentConfig.from_variant(variant)
    assert (config.planning_mode, config.source_budget, config.verification_mode) == (
        expected_planning, expected_budget, expected_verification
    )


@pytest.mark.parametrize(
    ("variant", "field", "replacement", "expected_fragment"),
    [
        ("D6", "planning_mode", "planner", "trace.planning_mode"),
        ("P6", "planning_mode", "direct", "trace.planning_mode"),
        ("P6V", "verification_mode", "none", "trace.verification_mode"),
        ("D6", "verification_mode", "verify", "trace.verification_mode"),
        ("P6", "source_budget", 3, "trace.source_budget"),
        ("P6V", "source_budget", 3, "trace.source_budget"),
    ],
)
def test_self_consistent_wrong_treatment_factors_are_rejected(
    tmp_path, variant, field, replacement, expected_fragment
):
    path, experiment, trace = _make_cell(tmp_path, variant)
    experiment[field] = replacement
    trace[field] = replacement
    if field == "planning_mode":
        query_count = 1 if replacement == "direct" else 4
        trace["query_count"] = trace["search_call_count"] = query_count
    if field == "verification_mode":
        trace["verification_status"] = (
            "ok" if replacement == "verify" else "not_requested"
        )
        trace["verified_claim_count"] = 2 if replacement == "verify" else 0
    if field == "source_budget":
        urls = trace["scheduled_urls"][:replacement]
        trace.update(
            source_count=replacement, successful_source_count=replacement,
            scheduled_urls=urls, successful_urls=list(urls),
        )
    _save(path, experiment, trace)
    errors = validate_pilot(tmp_path)
    assert any(expected_fragment in error for error in errors)


@pytest.mark.parametrize("field,replacement", [
    ("planning_mode", "planner"),
    ("source_budget", 3),
    ("verification_mode", "verify"),
])
def test_experiment_metadata_factor_disagreement_rejected(
    tmp_path, field, replacement
):
    path, experiment, trace = _make_cell(tmp_path, "D6")
    experiment[field] = replacement
    _save(path, experiment, trace)
    assert any(f"experiment.{field}" in e for e in validate_pilot(tmp_path))


@pytest.mark.parametrize("field", ["planning_mode", "source_budget", "verification_mode"])
def test_missing_required_trace_factor_fails_closed(tmp_path, field):
    path, experiment, trace = _make_cell(tmp_path, "P6")
    trace.pop(field)
    _save(path, experiment, trace)
    assert any(f"trace.{field}" in e for e in validate_pilot(tmp_path))


def test_legacy_omitted_experiment_factor_is_allowed_when_trace_is_frozen(tmp_path):
    path, experiment, trace = _make_cell(tmp_path, "D6")
    experiment.pop("planning_mode")
    experiment.pop("verification_mode")
    _save(path, experiment, trace)
    assert validate_pilot(tmp_path) == []


def test_null_experiment_factor_is_not_treated_as_absent(tmp_path):
    path, experiment, trace = _make_cell(tmp_path, "D6")
    experiment["planning_mode"] = None
    _save(path, experiment, trace)
    assert any("experiment.planning_mode" in e for e in validate_pilot(tmp_path))


def test_bool_is_not_an_integer_budget(tmp_path):
    path, experiment, trace = _make_cell(tmp_path, "D6")
    experiment["source_budget"] = trace["source_budget"] = True
    _save(path, experiment, trace)
    assert any("trace.source_budget" in e for e in validate_pilot(tmp_path))
