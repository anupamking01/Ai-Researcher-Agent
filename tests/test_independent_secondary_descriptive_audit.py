"""Independent consistency checks for frozen exploratory secondary descriptives.

Mutations operate on in-memory copies of preserved measurements; no treatments,
evaluator calls, human ratings, or canonical analysis outputs are generated.
"""
import copy
from functools import lru_cache
import json

import pytest
import scripts.audit_primary_inference_independently as auditor
from scripts.validate_main_study_inputs import read_csv_rows


# Reuse exact checked bootstrap calculations while exercising many unrelated
# secondary-contract mutations; the original bootstrap itself has separate tests.
_original_bootstrap = auditor._bootstrap_percentile_interval


@lru_cache(maxsize=3)
def _cached_bootstrap(values, seed, draws):
    return _original_bootstrap(list(values), seed=seed, draws=draws)


@pytest.fixture(autouse=True)
def cache_unchanged_primary_bootstrap(monkeypatch):
    monkeypatch.setattr(
        auditor, "_bootstrap_percentile_interval",
        lambda differences, *, seed, draws: _cached_bootstrap(
            tuple(differences), seed, draws
        ),
    )


@pytest.fixture
def frozen_evidence():
    root = auditor.ROOT
    return (
        read_csv_rows(root / "outputs/main_study_runs.csv"),
        read_csv_rows(root / "outputs/posthoc_support_runs.csv"),
        json.loads((root / "outputs/main_study_inference.json").read_text()),
    )


def test_independently_matches_all_frozen_secondary_point_descriptives(frozen_evidence):
    result = auditor.audit_primary(*frozen_evidence)
    assert result["secondary_variant_means_checked"] == 32
    assert result["secondary_paired_descriptives_checked"] == 24
    assert result["primary_contrasts_checked"] == 3


@pytest.mark.parametrize("metric", [
    "broad_support_rate", "unsupported_or_contradicted_rate",
    "successful_sources", "total_tokens", "treatment_cost_usd",
    "latency_seconds", "model_calls", "report_words",
])
def test_rejects_altered_secondary_variant_means(frozen_evidence, metric):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    changed["variant_summary"]["P6"]["means"][metric] += 0.25
    with pytest.raises(ValueError, match="P6.mean_" + metric):
        auditor.audit_primary(main, evaluator, changed)


@pytest.mark.parametrize("metric", [
    "broad_support_rate", "unsupported_or_contradicted_rate",
    "successful_sources", "total_tokens", "treatment_cost_usd",
    "latency_seconds", "model_calls", "report_words",
])
def test_rejects_altered_secondary_paired_effects(frozen_evidence, metric):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    changed["secondary_paired_descriptives"]["P6_minus_D6_planning"][metric][
        "mean_difference"
    ] += 0.25
    with pytest.raises(ValueError, match="P6_minus_D6_planning." + metric):
        auditor.audit_primary(main, evaluator, changed)


def test_rejects_altered_secondary_task_effect_without_changing_mean(frozen_evidence):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    diffs = changed["secondary_paired_descriptives"][
        "D6_minus_D3_retrieval_depth"
    ]["treatment_cost_usd"]["task_differences"]
    diffs[0], diffs[1] = diffs[1], diffs[0]
    with pytest.raises(ValueError, match="task_differences"):
        auditor.audit_primary(main, evaluator, changed)


def test_rejects_altered_zero_evidence_count(frozen_evidence):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    changed["variant_summary"]["D3"]["zero_evidence_runs"] += 1
    with pytest.raises(ValueError, match="zero_evidence_runs"):
        auditor.audit_primary(main, evaluator, changed)


def test_rejects_missing_secondary_paired_metric(frozen_evidence):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    del changed["secondary_paired_descriptives"]["P6V_minus_P6_verification"][
        "report_words"
    ]
    with pytest.raises(ValueError, match="secondary paired metric schema mismatch"):
        auditor.audit_primary(main, evaluator, changed)


def test_rejects_altered_secondary_direction_count(frozen_evidence):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    changed["secondary_paired_descriptives"]["P6_minus_D6_planning"][
        "successful_sources"
    ]["tied_tasks"] += 1
    with pytest.raises(ValueError, match="tied_tasks"):
        auditor.audit_primary(main, evaluator, changed)


def test_rejects_nonfinite_secondary_paired_statistic(frozen_evidence):
    main, evaluator, payload = frozen_evidence
    changed = copy.deepcopy(payload)
    changed["secondary_paired_descriptives"]["D6_minus_D3_retrieval_depth"][
        "latency_seconds"
    ]["paired_dz"] = float("nan")
    with pytest.raises(ValueError, match="paired_dz"):
        auditor.audit_primary(main, evaluator, changed)
