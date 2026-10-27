"""Independent read-only validation of frozen exploratory bootstrap intervals.

All mutations are confined to in-memory copies of the archived inference.
No new treatment, evaluator, or human-annotation observations are generated.
"""
import copy
from functools import lru_cache
from fractions import Fraction
import json
import random

import pytest

import scripts.audit_primary_inference_independently as auditor
from scripts.validate_main_study_inputs import read_csv_rows


# Existing primary intervals have dedicated regression coverage. Cache their
# unchanged calculations while these tests vary only exploratory JSON fields.
_original_primary_bootstrap = auditor._bootstrap_percentile_interval


@lru_cache(maxsize=3)
def _cached_primary(values, seed, draws):
    return _original_primary_bootstrap(list(values), seed=seed, draws=draws)


@pytest.fixture(autouse=True)
def cache_unchanged_primary_intervals(monkeypatch):
    monkeypatch.setattr(
        auditor, "_bootstrap_percentile_interval",
        lambda differences, *, seed, draws: _cached_primary(
            tuple(differences), seed, draws
        ),
    )


@pytest.fixture(scope="module")
def retained_evidence():
    root = auditor.ROOT
    return (
        read_csv_rows(root / "outputs/main_study_runs.csv"),
        read_csv_rows(root / "outputs/posthoc_support_runs.csv"),
        json.loads((root / "outputs/main_study_inference.json").read_text()),
    )


def test_independently_matches_all_24_retained_exploratory_intervals(
    retained_evidence,
):
    result = auditor.audit_primary(*retained_evidence)
    assert result["primary_contrasts_checked"] == 3
    assert result["secondary_bootstrap_intervals_checked"] == 24
    assert result["secondary_paired_descriptives_checked"] == 24


@pytest.mark.parametrize("contrast,metric", [
    ("D6_minus_D3_retrieval_depth", "broad_support_rate"),
    ("D6_minus_D3_retrieval_depth", "latency_seconds"),
    ("P6_minus_D6_planning", "total_tokens"),
    ("P6_minus_D6_planning", "treatment_cost_usd"),
    ("P6V_minus_P6_verification", "report_words"),
    ("P6V_minus_P6_verification", "unsupported_or_contradicted_rate"),
])
@pytest.mark.parametrize("endpoint", [0, 1])
def test_rejects_tampered_exploratory_bootstrap_endpoint(
    retained_evidence, contrast, metric, endpoint,
):
    treatment, evaluator, payload = retained_evidence
    modified = copy.deepcopy(payload)
    modified["secondary_paired_descriptives"][contrast][metric][
        "bootstrap_95pct_ci_mean_difference"
    ][endpoint] += 0.125
    with pytest.raises(ValueError, match="bootstrap_95pct_ci_mean_difference"):
        auditor.audit_primary(treatment, evaluator, modified)


@pytest.mark.parametrize("invalid", [
    None,
    [],
    [0.5],
    [0.1, 0.2, 0.3],
    [True, 0.2],
    ["0.1", 0.2],
    [float("nan"), 0.2],
    [float("inf"), 0.2],
])
def test_rejects_missing_malformed_nonfinite_secondary_interval(
    retained_evidence, invalid,
):
    treatment, evaluator, payload = retained_evidence
    modified = copy.deepcopy(payload)
    modified["secondary_paired_descriptives"][
        "D6_minus_D3_retrieval_depth"
    ]["model_calls"]["bootstrap_95pct_ci_mean_difference"] = invalid
    with pytest.raises(ValueError, match="bootstrap"):
        auditor.audit_primary(treatment, evaluator, modified)


def test_integer_scaled_bootstrap_matches_direct_fraction_oracle():
    # Synthetic rational effects test the independent scaled-integer arithmetic,
    # including non-integer interpolated percentiles, with no archived outcomes.
    effects = (
        Fraction(1, 3), Fraction(-2, 5), Fraction(7, 11),
        Fraction(0), Fraction(-9, 8),
    )
    seed, draws = 4567, 113
    rng = random.Random(seed)
    means = sorted(
        sum((effects[rng.randrange(len(effects))] for _ in effects), Fraction(0))
        / len(effects)
        for _ in range(draws)
    )
    def oracle(numerator):
        at = Fraction((draws - 1) * numerator, 40)
        lower = at.numerator // at.denominator
        upper = min(lower + 1, draws - 1)
        return means[lower] + (means[upper] - means[lower]) * (at - lower)

    assert auditor._secondary_bootstrap_ci(
        effects, seed=seed, draws=draws,
    ) == (oracle(1), oracle(39))


def test_secondary_bootstrap_retains_exact_constant_and_zero_effects():
    assert auditor._secondary_bootstrap_ci(
        (Fraction(1, 7),) * 10, seed=20261014, draws=101,
    ) == (Fraction(1, 7), Fraction(1, 7))
    assert auditor._secondary_bootstrap_ci(
        (Fraction(0),) * 10, seed=20261014, draws=101,
    ) == (Fraction(0), Fraction(0))
