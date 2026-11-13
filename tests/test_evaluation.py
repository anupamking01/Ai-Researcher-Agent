from dataclasses import replace
import json

import pytest

from logic.evaluation import (
    RunTrace,
    MAX_DIAGNOSTIC_REFERENCE_TASKS,
    _validated_reference_task_manifest,
    aggregate_runs,
    aggregate_runs_by_task,
    bootstrap_confidence_interval,
    deduplicate_sources,
    paired_metric_comparison,
    paired_metric_comparison_by_task,
    paired_bootstrap_confidence_interval_by_task,
    paired_run_trace_bootstrap_by_task,
    population_stddev,
    safe_mean,
    safe_median,
)


def test_run_trace_metrics():
    trace = RunTrace(
        run_id="run-1",
        completed=True,
        source_count=10,
        failed_source_count=2,
        citation_count=8,
        unsupported_claim_count=1,
        prompt_tokens=100,
        completion_tokens=50,
    )

    assert trace.total_tokens == 150
    assert trace.source_success_rate == 0.8
    assert trace.citation_precision_proxy == 0.875


@pytest.mark.parametrize(
    "invalid",
    [None, "False", "True", "", 0, 1, -1, 0.0, 1.0, [], {}, ()],
)
def test_run_trace_rejects_non_boolean_completion_before_aggregation(invalid):
    # Python truthiness would otherwise turn "False" and -1 into success.
    with pytest.raises(ValueError, match="completed must be a Boolean"):
        RunTrace(
            run_id="invalid-completion",
            completed=invalid,
            source_count=0,
        )


def test_run_trace_boolean_completion_retains_failed_runs_in_generic_summary():
    complete = RunTrace(run_id="success", completed=True, source_count=1)
    failed = RunTrace(run_id="failed", completed=False, source_count=0)
    assert complete.to_dict()["completed"] is True
    assert failed.to_dict()["completed"] is False
    assert aggregate_runs([complete, failed])["completion_rate"] == 0.5
    assert aggregate_runs([failed, failed])["completion_rate"] == 0.0


@pytest.mark.parametrize(
    ("source_count", "failed_source_count"),
    [
        (-1, 0),
        (0, -1),
        (1, 2),
        (True, 0),
        (1, False),
        (1.0, 0),
        (2, 1.0),
        ("2", 0),
    ],
)
def test_run_trace_fails_closed_on_impossible_source_accounting(
    source_count, failed_source_count
):
    with pytest.raises(ValueError, match="source_count|failed_source_count"):
        RunTrace(
            run_id="invalid-diagnostic",
            completed=False,
            source_count=source_count,
            failed_source_count=failed_source_count,
        )


@pytest.mark.parametrize(
    ("attempted", "failed", "successful", "rate"),
    [(0, 0, 0, 0.0), (3, 0, 3, 1.0), (3, 3, 0, 0.0), (4, 1, 3, 0.75)],
)
def test_run_trace_source_accounting_conserves_attempts(
    attempted, failed, successful, rate
):
    trace = RunTrace(
        run_id="accounting-fixture",
        completed=True,
        source_count=attempted,
        failed_source_count=failed,
    )
    assert trace.successful_source_count == successful
    assert trace.source_success_rate == rate
    summary = trace.to_dict()
    assert summary["successful_source_count"] + trace.failed_source_count == attempted
    assert summary["source_success_rate"] == rate



@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        (field, invalid)
        for field in (
            "citation_count",
            "supported_claim_count",
            "partially_supported_claim_count",
            "unsupported_claim_count",
            "contradicted_claim_count",
        )
        for invalid in (-1, True, 1.0, "1")
    ],
)
def test_run_trace_rejects_invalid_claim_accounting(field, invalid):
    counts = {
        "citation_count": 4,
        "supported_claim_count": 1,
        "partially_supported_claim_count": 1,
        "unsupported_claim_count": 1,
        "contradicted_claim_count": 1,
    }
    counts[field] = invalid
    with pytest.raises(ValueError, match=field):
        RunTrace(
            run_id="invalid-claim-telemetry",
            completed=True,
            source_count=1,
            **counts,
        )


@pytest.mark.parametrize(
    ("labels", "expected_rate"),
    [
        ((0, 0, 0, 0), 0.0),
        ((3, 0, 1, 0), 0.75),
        ((0, 1, 2, 1), 0.0),
        ((2, 1, 1, 0), 0.5),
    ],
)
def test_run_trace_claim_accounting_is_bounded_and_conserved(
    labels, expected_rate
):
    supported, partial, unsupported, contradicted = labels
    claims_checked = sum(labels)
    trace = RunTrace(
        run_id="valid-claim-telemetry",
        completed=True,
        source_count=1,
        citation_count=claims_checked,
        supported_claim_count=supported,
        partially_supported_claim_count=partial,
        unsupported_claim_count=unsupported,
        contradicted_claim_count=contradicted,
    )
    assert trace.verified_claim_count == claims_checked
    assert trace.claim_support_rate == expected_rate
    assert 0.0 <= trace.claim_support_rate <= 1.0
    assert trace.to_dict()["claim_support_rate"] == expected_rate


def test_run_trace_keeps_citations_distinct_from_claim_labels():
    # A citation count need not equal a claim-label partition; do not add
    # an unjustified cross-unit constraint to the generic diagnostic helper.
    trace = RunTrace(
        run_id="different-units",
        completed=True,
        source_count=1,
        citation_count=1,
        unsupported_claim_count=2,
    )
    assert trace.verified_claim_count == 2
    assert trace.claim_support_rate == 0.0
    assert trace.citation_precision_proxy == 0.0


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        (field, invalid)
        for field in (
            "prompt_tokens",
            "completion_tokens",
            "source_budget",
            "query_count",
            "search_call_count",
            "model_call_count",
            "unavailable_usage_call_count",
        )
        for invalid in (-1, False, 1.5, "2")
    ],
)
def test_run_trace_rejects_invalid_resource_counts(field, invalid):
    counts = {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "source_budget": 4,
        "query_count": 2,
        "search_call_count": 1,
        "model_call_count": 2,
        "unavailable_usage_call_count": 1,
    }
    counts[field] = invalid
    with pytest.raises(ValueError, match=field):
        RunTrace(
            run_id="invalid-budget-telemetry",
            completed=True,
            source_count=1,
            **counts,
        )


@pytest.mark.parametrize("field", ["latency_seconds", "estimated_cost_usd", "temperature"])
@pytest.mark.parametrize(
    "invalid",
    [-1, -0.01, True, "1", None, float("nan"), float("inf"), float("-inf"), 10**400],
)
def test_run_trace_rejects_invalid_numeric_telemetry_and_temperature(field, invalid):
    with pytest.raises(ValueError, match=field):
        RunTrace(
            run_id="invalid-finite-telemetry",
            completed=False,
            source_count=0,
            **{field: invalid},
        )


@pytest.mark.parametrize("temperature", [0, 0.0, 0.7, 1.0, 2, 1e-320])
def test_run_trace_preserves_finite_sampling_temperature_as_serializable_provenance(temperature):
    trace = RunTrace(
        run_id="finite-temperature", completed=True, source_count=1,
        temperature=temperature,
    )
    assert trace.temperature == temperature
    assert trace.to_dict()["temperature"] == temperature
    assert json.loads(json.dumps(trace.to_dict(), allow_nan=False))["temperature"] == temperature


@pytest.mark.parametrize(
    ("model_calls", "unavailable_calls"),
    [(0, 1), (2, 3)],
)
def test_run_trace_rejects_impossible_missing_usage_call_ledger(
    model_calls, unavailable_calls
):
    with pytest.raises(ValueError, match="unavailable_usage_call_count"):
        RunTrace(
            run_id="bad-call-accounting",
            completed=False,
            source_count=0,
            model_call_count=model_calls,
            unavailable_usage_call_count=unavailable_calls,
        )


def test_run_trace_accepts_valid_resource_boundaries_and_aggregates():
    runs = [
        RunTrace(
            run_id="complete-usage",
            completed=True,
            source_count=2,
            source_budget=2,
            prompt_tokens=100,
            completion_tokens=50,
            query_count=2,
            search_call_count=2,
            model_call_count=3,
            unavailable_usage_call_count=1,
            latency_seconds=2,
            estimated_cost_usd=0.25,
        ),
        RunTrace(
            run_id="zero-usage",
            completed=False,
            source_count=0,
            model_call_count=0,
            unavailable_usage_call_count=0,
            latency_seconds=0.0,
            estimated_cost_usd=0.0,
        ),
    ]
    assert runs[0].to_dict()["total_tokens"] == 150
    assert aggregate_runs(runs)["avg_total_tokens"] == 75.0
    assert aggregate_runs(runs)["avg_estimated_cost_usd"] == 0.125
    assert aggregate_runs(runs)["avg_latency_seconds"] == 1.0


def test_aggregate_runs():
    runs = [
        RunTrace(run_id="run-1", completed=True, source_count=10, failed_source_count=2, latency_seconds=20.0, prompt_tokens=100, completion_tokens=50, estimated_cost_usd=0.05),
        RunTrace(run_id="run-2", completed=False, source_count=5, failed_source_count=5, latency_seconds=10.0, prompt_tokens=50, completion_tokens=25, estimated_cost_usd=0.02),
    ]
    summary = aggregate_runs(runs)
    assert summary["n_runs"] == 2
    assert summary["completion_rate"] == 0.5
    assert summary["avg_sources"] == 7.5
    assert summary["avg_source_success_rate"] == 0.4
    assert summary["avg_latency_seconds"] == 15.0
    assert summary["median_latency_seconds"] == 15.0
    assert summary["latency_stddev_seconds"] == 5.0
    assert summary["avg_total_tokens"] == 112.5
    assert summary["total_tokens_stddev"] == 37.5
    assert summary["avg_estimated_cost_usd"] == pytest.approx(0.035)
    assert summary["median_estimated_cost_usd"] == pytest.approx(0.035)


def test_empty_aggregate_is_defined():
    summary = aggregate_runs([])
    assert summary["n_runs"] == 0
    assert summary["completion_rate"] == 0.0
    assert summary["median_latency_seconds"] == 0.0
    assert summary["latency_stddev_seconds"] == 0.0
    assert summary["total_tokens_stddev"] == 0.0
    assert summary["median_estimated_cost_usd"] == 0.0


def test_robust_statistics_handle_odd_even_and_empty_inputs():
    assert safe_median([]) == 0.0
    assert safe_median([9.0]) == 9.0
    assert safe_median([1.0, 9.0, 3.0]) == 3.0
    assert safe_median([1.0, 7.0, 3.0, 5.0]) == 4.0
    assert population_stddev([]) == 0.0
    assert population_stddev([2.0, 2.0, 2.0]) == 0.0
    assert population_stddev([10.0, 20.0]) == 5.0


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([1e308, 1e308], 1e308),
        ([-1e308, -1e308], -1e308),
        ([-1e308, 1e308], 0.0),
        ([1e308, 1e308, -1e308], 1e308 / 3),
        ([5e-324, 5e-324], 5e-324),
    ],
)
def test_safe_mean_retains_representable_large_and_subnormal_centers(values, expected):
    observed = safe_mean(values)
    assert observed == expected if expected == 5e-324 else observed == pytest.approx(expected)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([1e308, 1e308], 1e308),
        ([-1e308, -1e308], -1e308),
        ([-1e308, 1e308], 0.0),
        ([5e-324, 5e-324], 5e-324),
    ],
)
def test_safe_median_retains_representable_large_and_subnormal_centers(values, expected):
    assert safe_median(values) == expected


def test_bootstrap_confidence_interval_is_reproducible_and_bounded():
    first = bootstrap_confidence_interval([1, 2, 3, 4, 5], n_resamples=500, seed=42)
    second = bootstrap_confidence_interval([1, 2, 3, 4, 5], n_resamples=500, seed=42)
    assert first == second
    assert first["estimate"] == 3.0
    assert 1.0 <= first["lower"] <= first["estimate"] <= first["upper"] <= 5.0


def test_bootstrap_confidence_interval_handles_empty_and_invalid_settings():
    empty = bootstrap_confidence_interval([], n_resamples=10)
    assert empty["estimate"] == empty["lower"] == empty["upper"] == 0.0
    with pytest.raises(ValueError, match="confidence"):
        bootstrap_confidence_interval([1.0], confidence=1.0)
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_confidence_interval([1.0], n_resamples=0)


@pytest.mark.parametrize(
    "invalid", [0, 1, -1, True, False, 2.0, "50", None, [], {}, 10**400]
)
def test_generic_bootstrap_requires_explicit_multiple_integer_draws(invalid):
    with pytest.raises(ValueError, match="n_resamples"):
        bootstrap_confidence_interval([0.25, 0.75], n_resamples=invalid)


@pytest.mark.parametrize(
    "invalid", [True, False, None, 0.5, "1", [], {}]
)
def test_generic_bootstrap_requires_explicit_integer_seed(invalid):
    with pytest.raises(ValueError, match="seed"):
        bootstrap_confidence_interval([0.25, 0.75], seed=invalid)


@pytest.mark.parametrize(
    "invalid",
    [True, False, "0.95", None, float("nan"), float("inf"),
     float("-inf"), 0, 1, -1, 10**400],
)
def test_generic_bootstrap_requires_finite_numeric_confidence(invalid):
    with pytest.raises(ValueError, match="confidence"):
        bootstrap_confidence_interval([0.25, 0.75], confidence=invalid)


def test_generic_bootstrap_rejects_bad_settings_before_consuming_observations():
    class ForbidIteration:
        def __iter__(self):
            raise AssertionError("invalid settings consumed diagnostic inputs")

    with pytest.raises(ValueError, match="seed"):
        bootstrap_confidence_interval(ForbidIteration(), seed="3")


def test_generic_bootstrap_preserves_valid_seeded_intervals_and_empty_input():
    first = bootstrap_confidence_interval(
        [0.0, 0.25, 0.75], confidence=0.9, n_resamples=25, seed=-7
    )
    second = bootstrap_confidence_interval(
        [0.0, 0.25, 0.75], confidence=0.9, n_resamples=25, seed=-7
    )
    assert first == second
    assert first["confidence"] == 0.9
    assert first["n_resamples"] == 25
    assert bootstrap_confidence_interval(
        [], confidence=0.9, n_resamples=2, seed=-7
    )["estimate"] == 0.0


def test_bootstrap_confidence_interval_uses_linear_percentiles(monkeypatch):
    samples = iter(([0.0], [10.0], [20.0], [30.0]))

    class FixedRandom:
        def __init__(self, seed):
            assert seed == 0

        def choices(self, population, *, k):
            assert population == [0.0]
            assert k == 1
            return next(samples)

    monkeypatch.setattr("logic.evaluation.Random", FixedRandom)

    interval = bootstrap_confidence_interval(
        [0.0], confidence=0.5, n_resamples=4, seed=0
    )

    assert interval["lower"] == pytest.approx(7.5)
    assert interval["upper"] == pytest.approx(22.5)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_bootstrap_confidence_interval_rejects_non_finite_samples(invalid):
    with pytest.raises(ValueError, match="bootstrap sample must be finite"):
        bootstrap_confidence_interval([1.0, invalid], n_resamples=10)


def test_bootstrap_confidence_interval_rejects_non_finite_statistic():
    with pytest.raises(ValueError, match="bootstrap statistic must be finite"):
        bootstrap_confidence_interval(
            [1.0, 2.0], statistic=lambda values: float("nan"), n_resamples=10
        )


@pytest.mark.parametrize("invalid", [True, False, "1.0", None, 10**400])
def test_bootstrap_rejects_coerced_or_unrepresentable_sample_metric(invalid):
    # A coercible status/string is not an observed research measurement.
    with pytest.raises(ValueError, match="bootstrap sample must be finite"):
        bootstrap_confidence_interval([1.0, invalid], n_resamples=10)


@pytest.mark.parametrize("invalid", [True, "3.0", None, 10**400])
def test_bootstrap_rejects_coerced_or_unrepresentable_statistic(invalid):
    with pytest.raises(ValueError, match="bootstrap statistic must be finite"):
        bootstrap_confidence_interval(
            [1.0, 2.0], statistic=lambda values: invalid, n_resamples=10
        )


def test_bootstrap_confidence_interval_interpolates_extreme_finite_estimates():
    statistic_values = iter((-1e308, 1e308, 0.0))

    interval = bootstrap_confidence_interval(
        [0.0],
        statistic=lambda values: next(statistic_values),
        confidence=0.5,
        n_resamples=2,
    )

    assert interval["estimate"] == 0.0
    assert interval["lower"] == pytest.approx(-5e307)
    assert interval["upper"] == pytest.approx(5e307)


def test_bootstrap_mean_keeps_finite_extreme_constant_sample():
    interval = bootstrap_confidence_interval([1e308, 1e308], n_resamples=20, seed=7)
    assert interval["estimate"] == 1e308
    assert interval["lower"] == interval["upper"] == 1e308



@pytest.mark.parametrize("constant", [5e-324, -5e-324, 1e-320, -1e-320])
def test_bootstrap_percentiles_keep_constant_subnormal_effects(constant):
    # With 101 draws, the default 95% endpoints land halfway between two
    # order statistics. Multiplying both smallest-subnormal observations
    # by their 0.5 weights independently incorrectly produced zero.
    interval = bootstrap_confidence_interval(
        [constant], n_resamples=101, seed=17
    )
    assert interval["estimate"] == constant
    assert interval["lower"] == constant
    assert interval["upper"] == constant


def test_bootstrap_percentiles_keep_same_sign_subnormal_bounds():
    # Exercise interpolation through the public API with known ordered
    # statistic draws, not a private helper or any experiment outcomes.
    values = iter((5e-324, 1e-323, 0.0))
    interval = bootstrap_confidence_interval(
        [0.0],
        statistic=lambda sample: next(values),
        confidence=0.5,
        n_resamples=2,
    )
    assert interval["estimate"] == 0.0
    assert 5e-324 <= interval["lower"] <= interval["upper"] <= 1e-323


def test_paired_metric_comparison_preserves_task_pairing():
    summary = paired_metric_comparison(
        baseline=[2.0, 4.0, 3.0, 5.0],
        candidate=[3.0, 4.0, 2.0, 7.0],
    )
    assert summary["n_pairs"] == 4
    assert summary["mean_delta"] == pytest.approx(0.5)
    assert summary["median_delta"] == pytest.approx(0.5)
    assert summary["delta_stddev"] == pytest.approx(1.11803398875)
    assert summary["wins"] == 2
    assert summary["ties"] == 1
    assert summary["losses"] == 1


def test_paired_metric_comparison_handles_empty_and_rejects_misalignment():
    assert paired_metric_comparison([], []) == {
        "n_pairs": 0,
        "mean_delta": 0.0,
        "median_delta": 0.0,
        "delta_stddev": 0.0,
        "wins": 0,
        "ties": 0,
        "losses": 0,
    }
    with pytest.raises(ValueError, match="equal-length"):
        paired_metric_comparison([1.0], [1.0, 2.0])


@pytest.mark.parametrize("side", ["baseline", "candidate"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_paired_metric_comparison_rejects_non_finite_samples(side, invalid):
    baseline = [1.0]
    candidate = [2.0]
    if side == "baseline":
        baseline[0] = invalid
    else:
        candidate[0] = invalid

    with pytest.raises(ValueError, match=f"{side} values must be finite"):
        paired_metric_comparison(baseline, candidate)


@pytest.mark.parametrize("side", ["baseline", "candidate"])
@pytest.mark.parametrize("invalid", [True, False, "1.0", None, 10**400])
def test_positional_pairing_rejects_coerced_or_unrepresentable_metrics(
    side, invalid
):
    # The task-keyed API already rejected these, but the positional API
    # previously converted them to plausible floating-point observations.
    baseline = [1.0]
    candidate = [2.0]
    if side == "baseline":
        baseline[0] = invalid
    else:
        candidate[0] = invalid
    with pytest.raises(ValueError, match=f"{side} values must be finite"):
        paired_metric_comparison(baseline, candidate)


def test_paired_metric_comparison_rejects_overflowed_delta():
    with pytest.raises(ValueError, match="paired deltas must be finite"):
        paired_metric_comparison([-1e308], [1e308])


def test_paired_metric_comparison_keeps_finite_extreme_mean():
    # The two deltas and their true mean are finite; only the old sum overflowed.
    result = paired_metric_comparison([-1e308, -1e308], [0.0, 0.0])
    assert result["n_pairs"] == 2
    assert result["mean_delta"] == pytest.approx(1e308)
    assert result["median_delta"] == pytest.approx(1e308)
    assert result["delta_stddev"] == 0.0
    assert (result["wins"], result["ties"], result["losses"]) == (2, 0, 0)


def test_paired_metric_comparison_retains_finite_extreme_dispersion():
    # Opposing finite deltas have representable mean and population stddev.
    # Squaring them directly used to overflow and falsely reject this pair.
    result = paired_metric_comparison([0.0, 0.0], [1e308, -1e308])
    assert result["n_pairs"] == 2
    assert result["mean_delta"] == 0.0
    assert result["median_delta"] == 0.0
    assert result["delta_stddev"] == pytest.approx(1e308)
    assert (result["wins"], result["ties"], result["losses"]) == (1, 0, 1)


def test_task_keyed_pairing_joins_by_id_not_row_order():
    expected = ["task-c", "task-a", "task-b"]
    baseline = [("task-b", 2), ("task-c", 3), ("task-a", 1)]
    candidate = [("task-a", 2), ("task-b", 2), ("task-c", 1)]
    result = paired_metric_comparison_by_task(
        baseline, candidate, expected_task_ids=expected
    )
    assert result["task_ids"] == ["task-a", "task-b", "task-c"]
    assert result["n_pairs"] == 3
    assert result["mean_delta"] == pytest.approx(-1 / 3)
    assert (result["wins"], result["ties"], result["losses"]) == (1, 1, 1)
    assert result == paired_metric_comparison_by_task(
        reversed(baseline),
        reversed(candidate),
        expected_task_ids=reversed(expected),
    )


@pytest.mark.parametrize(
    ("baseline", "candidate", "message"),
    [
        ([("a", 1)], [("a", 2)], "baseline task coverage mismatch"),
        ([("a", 1), ("b", 1)], [("a", 2)], "candidate task coverage mismatch"),
        ([("a", 1), ("b", 1)], [("a", 2), ("x", 2)], "candidate task coverage mismatch"),
        ([("a", 1), ("a", 2), ("b", 3)], [("a", 1), ("b", 2)], "duplicate baseline"),
        ([("a", 1), ("b", 2)], [("a", 1), ("b", 2), ("b", 3)], "duplicate candidate"),
    ],
)
def test_task_keyed_pairing_rejects_missing_substituted_or_replicated_cells(
    baseline, candidate, message
):
    with pytest.raises(ValueError, match=message):
        paired_metric_comparison_by_task(
            baseline, candidate, expected_task_ids=["a", "b"]
        )


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ([], "must not be empty"),
        (["a", "a"], "duplicate expected"),
        (["a", ""], "expected task_id"),
        (["a", " b"], "expected task_id"),
    ],
)
def test_task_keyed_pairing_rejects_invalid_reference_task_set(expected, message):
    with pytest.raises(ValueError, match=message):
        paired_metric_comparison_by_task([], [], expected_task_ids=expected)


@pytest.mark.parametrize("bad_id", ["", " a", "a ", False, 1, None])
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_task_keyed_pairing_rejects_invalid_observed_task_ids(bad_id, arm):
    baseline, candidate = [("a", 1)], [("a", 2)]
    if arm == "baseline":
        baseline = [(bad_id, 1)]
    else:
        candidate = [(bad_id, 2)]
    with pytest.raises(ValueError, match=f"{arm} task_id"):
        paired_metric_comparison_by_task(
            baseline, candidate, expected_task_ids=["a"]
        )


@pytest.mark.parametrize(
    "bad_value",
    [False, "1", None, float("nan"), float("inf"), float("-inf"), 10**400],
)
@pytest.mark.parametrize("arm", ["baseline", "candidate"])
def test_task_keyed_pairing_rejects_non_numeric_or_nonfinite_metrics(
    bad_value, arm
):
    baseline, candidate = [("a", 1)], [("a", 2)]
    if arm == "baseline":
        baseline = [("a", bad_value)]
    else:
        candidate = [("a", bad_value)]
    with pytest.raises(ValueError, match=f"{arm} metric"):
        paired_metric_comparison_by_task(
            baseline, candidate, expected_task_ids=["a"]
        )


@pytest.mark.parametrize(
    "bad_record", [("a",), ("a", 1, 2), "a", {"task_id": "a"}]
)
def test_task_keyed_pairing_rejects_malformed_rows(bad_record):
    with pytest.raises(ValueError, match="records must be"):
        paired_metric_comparison_by_task(
            [bad_record], [("a", 1)], expected_task_ids=["a"]
        )


def test_task_keyed_pairing_accepts_finite_zero_and_generator_inputs():
    result = paired_metric_comparison_by_task(
        (item for item in [("b", 0.0), ("a", -1.0)]),
        (item for item in [("a", -1.0), ("b", 0.0)]),
        expected_task_ids=(task for task in ["a", "b"]),
    )
    assert result["task_ids"] == ["a", "b"]
    assert result["n_pairs"] == 2
    assert result["wins"] == result["losses"] == 0
    assert result["ties"] == 2



def _task_aggregate_trace(task_id, *, completed=True, **overrides):
    fields = {
        "run_id": f"run-{task_id}",
        "completed": completed,
        "source_count": 2,
        "variant_id": "D3",
        "task_set_id": "frozen-diagnostic",
        "task_id": task_id,
    }
    fields.update(overrides)
    return RunTrace(**fields)


def test_task_aggregate_checks_all_tasks_and_retains_failed_cells():
    rows = [
        _task_aggregate_trace("task-b", completed=False, source_count=0),
        _task_aggregate_trace("task-a", completed=True),
    ]
    result = aggregate_runs_by_task(
        rows,
        variant_id="D3",
        task_set_id="frozen-diagnostic",
        expected_task_ids=["task-b", "task-a"],
    )
    assert result["task_ids"] == ["task-a", "task-b"]
    assert result["n_runs"] == 2
    assert result["completion_rate"] == 0.5
    assert result["avg_sources"] == 1.0
    assert result == aggregate_runs_by_task(
        reversed(rows),
        variant_id="D3",
        task_set_id="frozen-diagnostic",
        expected_task_ids=reversed(["task-a", "task-b"]),
    )


@pytest.mark.parametrize(
    ("expected", "message"),
    [
        ([], "expected_task_ids must not be empty"),
        (["a", "a"], "duplicate expected task_id"),
        (["a", ""], "expected task_id"),
        (["a", " b"], "expected task_id"),
        (["a", " "], "expected task_id"),
        (["a", None], "expected task_id"),
        (["a", True], "expected task_id"),
    ],
)
def test_task_aggregate_rejects_invalid_reference_manifest(expected, message):
    with pytest.raises(ValueError, match=message):
        aggregate_runs_by_task(
            [], variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=expected,
        )


@pytest.mark.parametrize("field", ["variant_id", "task_set_id"])
@pytest.mark.parametrize("invalid", ["", " ", " D3", None, False, 123])
def test_task_aggregate_rejects_invalid_required_identity(field, invalid):
    arguments = {
        "variant_id": "D3",
        "task_set_id": "frozen-diagnostic",
    }
    arguments[field] = invalid
    with pytest.raises(ValueError, match=field):
        aggregate_runs_by_task(
            [_task_aggregate_trace("a")], expected_task_ids=["a"], **arguments
        )


@pytest.mark.parametrize(
    ("observed", "message"),
    [
        ([], "task coverage mismatch"),
        ([_task_aggregate_trace("a")], "task coverage mismatch"),
        ([_task_aggregate_trace("a"), _task_aggregate_trace("x")], "task coverage mismatch"),
        ([_task_aggregate_trace("a"), _task_aggregate_trace("a")], "duplicate observed task_id"),
        (
            [_task_aggregate_trace("a"), _task_aggregate_trace("b", run_id="run-a")],
            "duplicate run_id",
        ),
    ],
)
def test_task_aggregate_rejects_incomplete_substituted_or_duplicate_runs(
    observed, message
):
    with pytest.raises(ValueError, match=message):
        aggregate_runs_by_task(
            observed, variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a", "b"],
        )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"variant_id": "D6"}, "variant_id mismatch"),
        ({"task_set_id": "other"}, "task_set_id mismatch"),
        ({"completed": "false"}, "completed must be a Boolean"),
        ({"completed": 1}, "completed must be a Boolean"),
        ({"task_id": ""}, "observed task_id"),
        ({"task_id": " "}, "observed task_id"),
        ({"task_id": " a"}, "observed task_id"),
        ({"run_id": " "}, "run_id"),
        ({"run_id": None}, "run_id"),
    ],
)
def test_task_aggregate_rejects_corrupt_identity_or_completion(override, message):
    with pytest.raises(ValueError, match=message):
        aggregate_runs_by_task(
            [replace(_task_aggregate_trace("a"), **override)],
            variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a"],
        )


def test_task_aggregate_rejects_non_trace_records():
    with pytest.raises(ValueError, match="RunTrace"):
        aggregate_runs_by_task(
            [("a", 2)], variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a"],
        )


def test_task_aggregate_accepts_one_pass_generators_and_zero_source_failures():
    result = aggregate_runs_by_task(
        (row for row in [
            _task_aggregate_trace("b", completed=False, source_count=0),
            _task_aggregate_trace("a", completed=False, source_count=0),
        ]),
        variant_id="D3", task_set_id="frozen-diagnostic",
        expected_task_ids=(task_id for task_id in ["b", "a"]),
    )
    assert result["task_ids"] == ["a", "b"]
    assert result["n_runs"] == 2
    assert result["completion_rate"] == 0.0
    assert result["avg_source_success_rate"] == 0.0




def test_task_aggregate_rejects_unbounded_distinct_stream_on_first_unknown_task():
    reads = []

    def stream():
        index = 0
        while True:
            reads.append(index)
            yield _task_aggregate_trace(f"unexpected-{index}")
            index += 1

    with pytest.raises(ValueError, match="task coverage mismatch"):
        aggregate_runs_by_task(
            stream(), variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=(task for task in ("a", "b")),
        )
    assert reads == [0]


def test_task_aggregate_rejects_unbounded_duplicate_stream_without_read_ahead():
    reads = []

    def stream():
        while True:
            reads.append(len(reads))
            yield _task_aggregate_trace("a")

    with pytest.raises(ValueError, match="duplicate observed task_id"):
        aggregate_runs_by_task(
            stream(), variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a", "b"],
        )
    assert reads == [0, 1]


def test_task_aggregate_rejects_extra_after_complete_arm_without_read_ahead():
    reads = []

    def stream():
        for task_id in ("b", "a", "extra"):
            reads.append(task_id)
            yield _task_aggregate_trace(task_id)
        raise AssertionError("unexpected extra source read")

    with pytest.raises(ValueError, match="task coverage mismatch"):
        aggregate_runs_by_task(
            stream(), variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a", "b"],
        )
    assert reads == ["b", "a", "extra"]


def test_task_aggregate_question_manifest_rejects_swapped_questions():
    """Task IDs alone cannot detect the correct prompt attached to wrong runs."""
    questions = {"a": "What is evidence A?", "b": "Why is B different?"}
    rows = [
        _task_aggregate_trace("a", question=questions["b"]),
        _task_aggregate_trace("b", question=questions["a"]),
    ]
    with pytest.raises(ValueError, match="task question mismatch"):
        aggregate_runs_by_task(
            rows, variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a", "b"], expected_questions_by_task=questions,
        )


def test_task_aggregate_question_manifest_accepts_exact_text_and_failed_runs():
    questions = {"a": "What is evidence A?", "b": "Why is B different?"}
    rows = [
        _task_aggregate_trace("b", completed=False, source_count=0, question=questions["b"]),
        _task_aggregate_trace("a", question=questions["a"]),
    ]
    result = aggregate_runs_by_task(
        (row for row in rows),
        variant_id="D3", task_set_id="frozen-diagnostic",
        expected_task_ids=(task_id for task_id in ["b", "a"]),
        expected_questions_by_task=questions,
    )
    assert result["task_ids"] == ["a", "b"]
    assert result["completion_rate"] == 0.5
    assert result == aggregate_runs_by_task(
        reversed(rows), variant_id="D3", task_set_id="frozen-diagnostic",
        expected_task_ids=reversed(["a", "b"]),
        expected_questions_by_task=dict(reversed(list(questions.items()))),
    )
    # Legacy callers can omit the new independent text contract.
    assert aggregate_runs_by_task(
        [_task_aggregate_trace("a")], variant_id="D3",
        task_set_id="frozen-diagnostic", expected_task_ids=["a"],
    )["n_runs"] == 1


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ([], "expected_questions_by_task must be a mapping"),
        ({}, "expected task question coverage mismatch"),
        ({"a": "Question?"}, "expected task question coverage mismatch"),
        ({"a": "Question?", "b": "Other?", "c": "Extra?"}, "expected task question coverage mismatch"),
        ({"a": "Question?", " b": "Other?"}, "expected question task_id"),
        ({1: "Question?", "b": "Other?"}, "expected question task_id"),
        ({"a": "", "b": "Other?"}, "expected task question"),
        ({"a": "  ", "b": "Other?"}, "expected task question"),
        ({"a": None, "b": "Other?"}, "expected task question"),
        ({"a": 123, "b": "Other?"}, "expected task question"),
        ({"a": True, "b": "Other?"}, "expected task question"),
    ],
)
def test_task_aggregate_rejects_corrupt_question_manifest_before_trace_reads(
    manifest, message
):
    def must_not_read():
        raise AssertionError("invalid independent manifest consumed trace records")
        yield None

    with pytest.raises(ValueError, match=message):
        aggregate_runs_by_task(
            must_not_read(), variant_id="D3",
            task_set_id="frozen-diagnostic", expected_task_ids=["a", "b"],
            expected_questions_by_task=manifest,
        )


@pytest.mark.parametrize(
    "observed",
    ["Different case?", "Question? ", " Question?", "", None, True, 42],
)
def test_task_aggregate_rejects_mismatched_or_nontext_trace_question(observed):
    with pytest.raises(ValueError, match="task question mismatch"):
        aggregate_runs_by_task(
            [_task_aggregate_trace("a", question=observed)],
            variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a"],
            expected_questions_by_task={"a": "Question?"},
        )


@pytest.mark.parametrize(
    ("record_overrides", "error"),
    [
        ([{"source_count": 10**400}], "aggregate run statistics must be finite"),
        ([{"prompt_tokens": 10**400}], "aggregate run statistics must be finite"),
    ],
)
def test_aggregate_runs_rejects_derived_overflow(record_overrides, error):
    """Finite/valid raw counters need not yield representable statistics."""
    traces = [
        RunTrace(run_id=f"overflow-{i}", completed=True, source_count=1, **row)
        if "source_count" not in row
        else RunTrace(run_id=f"overflow-{i}", completed=True, **row)
        for i, row in enumerate(record_overrides)
    ]
    with pytest.raises(ValueError, match=error):
        aggregate_runs(traces)


def test_task_keyed_aggregate_preserves_finite_extreme_cost_centers():
    traces = [
        _task_aggregate_trace("a", estimated_cost_usd=1e308),
        _task_aggregate_trace("b", estimated_cost_usd=1e308),
    ]
    result = aggregate_runs_by_task(
        traces, variant_id="D3", task_set_id="frozen-diagnostic",
        expected_task_ids=["a", "b"],
    )
    assert result["avg_estimated_cost_usd"] == pytest.approx(1e308)
    assert result["median_estimated_cost_usd"] == pytest.approx(1e308)


def test_task_keyed_aggregate_still_rejects_oversized_integer_counter():
    with pytest.raises(ValueError, match="aggregate run statistics must be finite"):
        aggregate_runs_by_task(
            [_task_aggregate_trace("a", prompt_tokens=10**400)],
            variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["a"],
        )


def test_aggregate_runs_preserves_finite_extreme_timing_and_cost_centers():
    traces = [
        RunTrace(
            run_id=f"finite-large-{index}", completed=True, source_count=1,
            latency_seconds=1e308, estimated_cost_usd=1e308,
        )
        for index in range(2)
    ]
    result = aggregate_runs(traces)
    assert result["avg_latency_seconds"] == pytest.approx(1e308)
    assert result["median_latency_seconds"] == pytest.approx(1e308)
    assert result["latency_stddev_seconds"] == 0.0
    assert result["avg_estimated_cost_usd"] == pytest.approx(1e308)
    assert result["median_estimated_cost_usd"] == pytest.approx(1e308)


@pytest.mark.parametrize("large", [1e100, 1e200])
def test_aggregate_runs_keeps_large_but_representable_statistics(large):
    traces = [
        RunTrace(run_id="a", completed=False, source_count=0,
                 latency_seconds=0.0, estimated_cost_usd=0.0),
        RunTrace(run_id="b", completed=True, source_count=1,
                 latency_seconds=large, estimated_cost_usd=large),
    ]
    result = aggregate_runs(traces)
    assert result["n_runs"] == 2
    assert result["completion_rate"] == 0.5
    assert result["avg_latency_seconds"] == pytest.approx(large / 2)
    assert result["latency_stddev_seconds"] == pytest.approx(large / 2)
    assert result["avg_estimated_cost_usd"] == pytest.approx(large / 2)


@pytest.mark.parametrize(
    ("observations", "expected"),
    [
        ([0.0, 1e200], 5e199),
        ([0.0, 1e308], 5e307),
        ([-1e308, 1e308], 1e308),
        ([1e308, 1e308], 0.0),
        ([0.0, 1e-200], 5e-201),
    ],
)
def test_population_stddev_avoids_spurious_intermediate_overflow(
    observations, expected
):
    assert population_stddev(observations) == pytest.approx(expected)


def test_task_keyed_aggregate_preserves_finite_extreme_latency_dispersion():
    traces = [
        _task_aggregate_trace("a", latency_seconds=0.0),
        _task_aggregate_trace("b", latency_seconds=1e200),
    ]
    summary = aggregate_runs_by_task(
        traces, variant_id="D3", task_set_id="frozen-diagnostic",
        expected_task_ids=["a", "b"],
    )
    assert summary["latency_stddev_seconds"] == pytest.approx(5e199)


def test_deduplicate_sources_preserves_order():
    urls = [" https://example.com/a ", "https://example.com/b", "https://example.com/a", "", "https://example.com/c"]
    assert deduplicate_sources(urls) == ["https://example.com/a", "https://example.com/b", "https://example.com/c"]

def test_task_keyed_bootstrap_resamples_complete_paired_differences():
    # Exact dyadic deltas make the paired effect and its constant interval
    # unambiguous without relying on live or historical outcome data.
    result = paired_bootstrap_confidence_interval_by_task(
        [("task-b", 0.5), ("task-a", 0.25)],
        [("task-a", 0.5), ("task-b", 0.75)],
        expected_task_ids=["task-b", "task-a"],
        n_resamples=101,
        seed=31,
    )
    assert result["task_ids"] == ["task-a", "task-b"]
    assert result["n_pairs"] == 2
    assert result["mean_delta"] == 0.25
    assert result["wins"] == 2
    assert result["bootstrap_method"] == "paired_percentile_mean_delta"
    assert result["bootstrap_confidence_interval"] == {
        "estimate": 0.25,
        "lower": 0.25,
        "upper": 0.25,
        "confidence": 0.95,
        "n_resamples": 101,
    }


def test_task_keyed_bootstrap_is_reproducible_across_generator_record_order():
    baseline = [("c", 0.0), ("a", 0.0), ("b", 0.0)]
    candidate = [("b", 0.5), ("c", -0.5), ("a", 1.0)]
    first = paired_bootstrap_confidence_interval_by_task(
        iter(baseline),
        iter(candidate),
        expected_task_ids=(task for task in ["c", "b", "a"]),
        n_resamples=211,
        confidence=0.9,
        seed=29,
    )
    second = paired_bootstrap_confidence_interval_by_task(
        iter(reversed(baseline)),
        iter(reversed(candidate)),
        expected_task_ids=(task for task in ["a", "c", "b"]),
        n_resamples=211,
        confidence=0.9,
        seed=29,
    )
    assert first == second
    assert first["task_ids"] == ["a", "b", "c"]
    assert first["bootstrap_confidence_interval"]["estimate"] == first["mean_delta"]
    assert -0.5 <= first["bootstrap_confidence_interval"]["lower"]
    assert first["bootstrap_confidence_interval"]["upper"] <= 1.0


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected", "message"),
    [
        ([("a", 0.0)], [("a", 0.5)], ["a", "b"], "coverage mismatch"),
        ([("a", 0.0), ("b", 0.0)],
         [("a", 0.5), ("x", 0.5)], ["a", "b"], "coverage mismatch"),
        ([("a", 0.0), ("a", 0.0)],
         [("a", 0.5)], ["a"], "duplicate baseline task_id"),
        ([("a", 0.0)], [("a", 0.5)], ["a", "a"], "duplicate expected task_id"),
        ([("a", True)], [("a", 0.5)], ["a"], "baseline metric"),
        ([("a", 0.0)], [("a", "0.5")], ["a"], "candidate metric"),
        ([("a", -1e308)], [("a", 1e308)], ["a"], "paired deltas"),
    ],
)
def test_task_keyed_bootstrap_fails_closed_on_invalid_pairing(
    baseline, candidate, expected, message
):
    with pytest.raises(ValueError, match=message):
        paired_bootstrap_confidence_interval_by_task(
            iter(baseline), iter(candidate),
            expected_task_ids=expected, n_resamples=7, seed=0,
        )


@pytest.mark.parametrize("invalid", [0, 1, -1, True, 2.0, "50", None])
def test_task_keyed_bootstrap_rejects_invalid_resample_count(invalid):
    with pytest.raises(ValueError, match="n_resamples"):
        paired_bootstrap_confidence_interval_by_task(
            [("a", 0.0)], [("a", 1.0)],
            expected_task_ids=["a"], n_resamples=invalid,
        )


@pytest.mark.parametrize("invalid", [True, None, 0.5, "1", [], {}])
def test_task_keyed_bootstrap_requires_explicit_integer_seed(invalid):
    with pytest.raises(ValueError, match="seed"):
        paired_bootstrap_confidence_interval_by_task(
            [("a", 0.0)], [("a", 1.0)],
            expected_task_ids=["a"], seed=invalid,
        )


@pytest.mark.parametrize(
    "invalid", [True, False, "0.95", None, float("nan"), float("inf"), 0, 1, 10**400]
)
def test_task_keyed_bootstrap_rejects_invalid_confidence(invalid):
    with pytest.raises(ValueError, match="confidence"):
        paired_bootstrap_confidence_interval_by_task(
            [("a", 0.0)], [("a", 1.0)],
            expected_task_ids=["a"], confidence=invalid,
        )


# Prospective-only RunTrace adapter: validate treatment identity and frozen
# question assignment before turning records into numeric paired observations.
_PAIR_QUESTIONS = {"a": "First research question?", "b": "Second research question?"}


def _paired_run_trace(task_id, variant, *, completed=True, **changes):
    values = {
        "run_id": f"{variant}-{task_id}",
        "completed": completed,
        "source_count": 2 if completed else 0,
        "supported_claim_count": 1 if completed else 0,
        "unsupported_claim_count": 1 if completed else 0,
        "variant_id": variant,
        "task_set_id": "prospective-paired",
        "task_id": task_id,
        "question": _PAIR_QUESTIONS[task_id],
    }
    values.update(changes)
    return RunTrace(**values)


def _compare_paired_traces(baseline, candidate, **settings):
    options = {"confidence": 0.9, "n_resamples": 101, "seed": 23}
    options.update(settings)
    return paired_run_trace_bootstrap_by_task(
        baseline,
        candidate,
        baseline_variant_id="D3",
        candidate_variant_id="D6",
        task_set_id="prospective-paired",
        expected_task_ids=(task for task in ("b", "a")),
        expected_questions_by_task=_PAIR_QUESTIONS,
        **options,
    )


def test_run_trace_bootstrap_retains_failed_zero_source_task_and_is_order_invariant():
    baseline = [
        _paired_run_trace("b", "D3", completed=False),
        _paired_run_trace("a", "D3"),
    ]
    candidate = [
        _paired_run_trace("a", "D6", supported_claim_count=2,
                          unsupported_claim_count=0),
        _paired_run_trace("b", "D6", completed=False),
    ]
    first = _compare_paired_traces(iter(baseline), iter(candidate))
    second = _compare_paired_traces(reversed(baseline), reversed(candidate))
    assert first == second
    assert first["task_ids"] == ["a", "b"]
    assert first["n_pairs"] == 2
    assert first["wins"] == 1
    assert first["ties"] == 1
    assert first["losses"] == 0
    assert first["mean_delta"] == 0.25
    assert first["bootstrap_confidence_interval"]["estimate"] == 0.25
    assert first["baseline_variant_id"] == "D3"
    assert first["candidate_variant_id"] == "D6"


@pytest.mark.parametrize(
    ("metric", "estimate"),
    [
        ("claim_support_rate", 0.25),
        ("source_success_rate", 0.0),
        ("citation_precision_proxy", 0.0),
    ],
)
def test_run_trace_bootstrap_supports_only_preselected_rate_metrics(metric, estimate):
    baseline = [_paired_run_trace("a", "D3"), _paired_run_trace("b", "D3", completed=False)]
    candidate = [
        _paired_run_trace("a", "D6", supported_claim_count=2,
                          unsupported_claim_count=0),
        _paired_run_trace("b", "D6", completed=False),
    ]
    assert paired_run_trace_bootstrap_by_task(
        baseline, candidate,
        baseline_variant_id="D3", candidate_variant_id="D6",
        task_set_id="prospective-paired", expected_task_ids=["a", "b"],
        expected_questions_by_task=_PAIR_QUESTIONS,
        metric=metric, n_resamples=101,
    )["mean_delta"] == estimate


@pytest.mark.parametrize("bad_metric", ["estimated_cost_usd", "question", "", None, True])
def test_run_trace_bootstrap_rejects_unapproved_or_non_numeric_metric(bad_metric):
    with pytest.raises(ValueError, match="supported higher-is-better"):
        _compare_paired_traces([], [], metric=bad_metric)


@pytest.mark.parametrize(
    ("arm", "change", "message"),
    [
        ("baseline", {"variant_id": "D6"}, "variant_id mismatch"),
        ("candidate", {"variant_id": "D3"}, "variant_id mismatch"),
        ("baseline", {"task_set_id": "other"}, "task_set_id mismatch"),
        ("candidate", {"task_set_id": "other"}, "task_set_id mismatch"),
        ("baseline", {"question": "Second research question?"}, "task question mismatch"),
        ("candidate", {"question": "Other question?"}, "task question mismatch"),
        ("baseline", {"task_id": "other"}, "task coverage mismatch"),
        ("candidate", {"task_id": "other"}, "task coverage mismatch"),
    ],
)
def test_run_trace_bootstrap_fails_before_sampling_on_mislabeled_cells(
    arm, change, message
):
    baseline = [_paired_run_trace("a", "D3"), _paired_run_trace("b", "D3")]
    candidate = [_paired_run_trace("a", "D6"), _paired_run_trace("b", "D6")]
    rows = baseline if arm == "baseline" else candidate
    rows[0] = replace(rows[0], **change)
    with pytest.raises(ValueError, match=message):
        _compare_paired_traces(baseline, candidate)


def test_run_trace_bootstrap_rejects_cross_arm_run_id_reuse():
    baseline = [_paired_run_trace("a", "D3"), _paired_run_trace("b", "D3")]
    candidate = [
        replace(_paired_run_trace("a", "D6"), run_id=baseline[0].run_id),
        _paired_run_trace("b", "D6"),
    ]
    with pytest.raises(ValueError, match="run_id reused across"):
        _compare_paired_traces(baseline, candidate)


@pytest.mark.parametrize(
    ("baseline", "candidate", "message"),
    [
        ([_paired_run_trace("a", "D3")], [_paired_run_trace("a", "D6"),
                                         _paired_run_trace("b", "D6")],
         "task coverage mismatch"),
        ([_paired_run_trace("a", "D3"), _paired_run_trace("a", "D3")],
         [_paired_run_trace("a", "D6"), _paired_run_trace("b", "D6")],
         "duplicate observed task_id"),
    ],
)
def test_run_trace_bootstrap_rejects_missing_and_duplicate_cells(
    baseline, candidate, message
):
    with pytest.raises(ValueError, match=message):
        _compare_paired_traces(baseline, candidate)


def test_run_trace_bootstrap_rejects_same_variant_and_invalid_resamples():
    with pytest.raises(ValueError, match="must differ"):
        paired_run_trace_bootstrap_by_task(
            [], [], baseline_variant_id="D3", candidate_variant_id="D3",
            task_set_id="prospective-paired", expected_task_ids=["a"],
            expected_questions_by_task={"a": "First research question?"},
        )
    with pytest.raises(ValueError, match="n_resamples"):
        _compare_paired_traces([], [], n_resamples=1)


def test_run_trace_bootstrap_rejects_nonindependent_reference_question_mapping():
    baseline = [_paired_run_trace("a", "D3"), _paired_run_trace("b", "D3")]
    candidate = [_paired_run_trace("a", "D6"), _paired_run_trace("b", "D6")]
    with pytest.raises(ValueError, match="task question mismatch"):
        paired_run_trace_bootstrap_by_task(
            baseline, candidate,
            baseline_variant_id="D3", candidate_variant_id="D6",
            task_set_id="prospective-paired", expected_task_ids=["a", "b"],
            expected_questions_by_task={"a": _PAIR_QUESTIONS["b"],
                                        "b": _PAIR_QUESTIONS["a"]},
            n_resamples=10,
        )


# Synthetic independent configuration references, not historic treatment data.
_PLANNED = {
    "D3": {
        "planning_mode": "direct", "verification_mode": "off", "source_budget": 3,
        "smart_model": "smart-v1", "fast_model": "fast-v1", "temperature": 0.0,
    },
    "D6": {
        "planning_mode": "direct", "verification_mode": "off", "source_budget": 6,
        "smart_model": "smart-v1", "fast_model": "fast-v1", "temperature": 0.0,
    },
}


def _planned_trace(task, variant, **changes):
    completed = changes.pop("completed", True)
    return replace(
        _paired_run_trace(task, variant, completed=completed),
        **{**_PLANNED[variant], **changes},
    )


def test_treatment_fidelity_optional_contract_detects_budget_drift():
    rows = [_planned_trace("a", "D3", source_budget=6)]
    opts = {
        "variant_id": "D3", "task_set_id": "prospective-paired",
        "expected_task_ids": ["a"],
        "expected_questions_by_task": {"a": _PAIR_QUESTIONS["a"]},
    }
    assert aggregate_runs_by_task(rows, **opts)["n_runs"] == 1
    with pytest.raises(ValueError, match="treatment setting mismatch for source_budget"):
        aggregate_runs_by_task(
            rows, expected_treatment_settings=_PLANNED["D3"], **opts
        )


def test_treatment_fidelity_preserves_failed_cells_and_seeded_pairing():
    baseline = [_planned_trace("b", "D3", completed=False, source_count=0),
                _planned_trace("a", "D3")]
    candidate = [_planned_trace("a", "D6", supported_claim_count=2,
                                unsupported_claim_count=0),
                 _planned_trace("b", "D6", completed=False, source_count=0)]
    old = _compare_paired_traces(baseline, candidate)
    bound = _compare_paired_traces(
        iter(baseline), iter(candidate),
        expected_treatment_settings_by_variant=_PLANNED,
    )
    reverse = _compare_paired_traces(
        reversed(baseline), reversed(candidate),
        expected_treatment_settings_by_variant=_PLANNED,
    )
    assert old == bound == reverse
    assert bound["task_ids"] == ["a", "b"]
    assert bound["n_pairs"] == 2


@pytest.mark.parametrize("variant", ["D3", "D6"])
@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("planning_mode", "planner"), ("verification_mode", "on"),
        ("source_budget", 9), ("smart_model", "other"),
        ("fast_model", "other"), ("temperature", 0.3),
    ],
)
def test_treatment_fidelity_detects_wrong_planned_setting_in_both_arms(
    variant, field, changed
):
    baseline = [_planned_trace("a", "D3"), _planned_trace("b", "D3")]
    candidate = [_planned_trace("a", "D6"), _planned_trace("b", "D6")]
    arm = baseline if variant == "D3" else candidate
    arm[0] = replace(arm[0], **{field: changed})
    with pytest.raises(ValueError, match=f"treatment setting mismatch for {field}"):
        _compare_paired_traces(
            baseline, candidate, expected_treatment_settings_by_variant=_PLANNED,
        )


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        ({}, "exactly six"), ({"source_budget": 3}, "exactly six"),
        ({**_PLANNED["D3"], "extra": 1}, "exactly six"),
        ({**_PLANNED["D3"], "source_budget": True}, "source_budget"),
        ({**_PLANNED["D3"], "source_budget": -1}, "source_budget"),
        ({**_PLANNED["D3"], "planning_mode": ""}, "planning_mode"),
        ({**_PLANNED["D3"], "verification_mode": " off"}, "verification_mode"),
        ({**_PLANNED["D3"], "smart_model": None}, "smart_model"),
        ({**_PLANNED["D3"], "temperature": True}, "temperature"),
        ({**_PLANNED["D3"], "temperature": "0"}, "temperature"),
        ({**_PLANNED["D3"], "temperature": float("nan")}, "temperature"),
        ({**_PLANNED["D3"], "temperature": -1.0}, "temperature"),
        ({**_PLANNED["D3"], "temperature": 10**400}, "temperature"),
    ],
)
def test_treatment_fidelity_invalid_plan_fails_before_consuming_runs(bad, message):
    def no_read():
        raise AssertionError("must not inspect observations with an invalid plan")
        yield None

    with pytest.raises(ValueError, match=message):
        aggregate_runs_by_task(
            no_read(), variant_id="D3", task_set_id="prospective-paired",
            expected_task_ids=["a"], expected_treatment_settings=bad,
        )


@pytest.mark.parametrize(
    "configs", [
        [], {}, {"D3": _PLANNED["D3"]},
        {**_PLANNED, "P6": _PLANNED["D3"]},
        {"D3": [], "D6": _PLANNED["D6"]},
    ],
)
def test_treatment_fidelity_paired_manifest_fails_before_arm_reads(configs):
    def no_read():
        raise AssertionError("must not inspect observed treatment arms")
        yield None

    with pytest.raises(ValueError, match="expected_treatment_settings"):
        _compare_paired_traces(
            no_read(), no_read(),
            expected_treatment_settings_by_variant=configs,
        )


# Independent reference inputs must be checked before reading observations.
@pytest.mark.parametrize("bad_ids", ["a", b"a", "", b""])
def test_task_reference_rejects_scalar_text_without_reading_observations(bad_ids):
    def no_read():
        raise AssertionError("malformed reference must not consume observations")
        yield None

    with pytest.raises(ValueError, match="expected_task_ids"):
        paired_metric_comparison_by_task(
            no_read(), no_read(), expected_task_ids=bad_ids
        )
    with pytest.raises(ValueError, match="expected_task_ids"):
        paired_bootstrap_confidence_interval_by_task(
            no_read(), no_read(), expected_task_ids=bad_ids,
            n_resamples=3,
        )
    with pytest.raises(ValueError, match="expected_task_ids"):
        aggregate_runs_by_task(
            no_read(), variant_id="D3", task_set_id="prospective-paired",
            expected_task_ids=bad_ids,
        )
    with pytest.raises(ValueError, match="expected_task_ids"):
        paired_run_trace_bootstrap_by_task(
            no_read(), no_read(),
            baseline_variant_id="D3", candidate_variant_id="D6",
            task_set_id="prospective-paired",
            expected_task_ids=bad_ids,
            expected_questions_by_task={"a": "First research question?"},
            n_resamples=3,
        )


@pytest.mark.parametrize(
    ("bad_ids", "error"),
    [
        ([], "must not be empty"),
        (["a", "a"], "duplicate expected task_id"),
        (["a", " b"], "expected task_id"),
        (["a", None], "expected task_id"),
    ],
)
def test_paired_trace_rejects_invalid_reference_ids_before_reading_arms(
    bad_ids, error
):
    def no_read():
        raise AssertionError("invalid independent task reference read an arm")
        yield None

    with pytest.raises(ValueError, match=error):
        paired_run_trace_bootstrap_by_task(
            no_read(), no_read(),
            baseline_variant_id="D3", candidate_variant_id="D6",
            task_set_id="prospective-paired", expected_task_ids=bad_ids,
            expected_questions_by_task={"a": _PAIR_QUESTIONS["a"]},
            n_resamples=3,
        )


@pytest.mark.parametrize(
    ("bad_questions", "error"),
    [
        ([], "expected_questions_by_task"),
        ({}, "coverage mismatch"),
        ({"a": _PAIR_QUESTIONS["a"]}, "coverage mismatch"),
        ({"a": "", "b": _PAIR_QUESTIONS["b"]}, "expected task question"),
        ({" a": "wrong", "b": _PAIR_QUESTIONS["b"]}, "expected question task_id"),
        ({"a": _PAIR_QUESTIONS["a"], "b": _PAIR_QUESTIONS["b"],
          "extra": "unexpected"}, "coverage mismatch"),
    ],
)
def test_paired_trace_preflights_reference_questions_before_reading_arms(
    bad_questions, error
):
    def no_read():
        raise AssertionError("invalid independent question reference read an arm")
        yield None

    with pytest.raises(ValueError, match=error):
        paired_run_trace_bootstrap_by_task(
            no_read(), no_read(),
            baseline_variant_id="D3", candidate_variant_id="D6",
            task_set_id="prospective-paired",
            expected_task_ids=(task for task in ["b", "a"]),
            expected_questions_by_task=bad_questions,
            n_resamples=3,
        )


# Fail closed on unbounded one-pass producers: the independent task matrix
# bounds reads, and a malformed baseline must not touch the candidate arm.
def test_run_trace_pairing_bounds_unending_baseline_without_consuming_candidate():
    reads = []

    def endless_baseline():
        while True:
            reads.append(1)
            yield _paired_run_trace("a", "D3")

    def unread_candidate():
        raise AssertionError("candidate arm read before baseline cardinality validation")
        yield None

    with pytest.raises(ValueError, match="baseline has more records"):
        _compare_paired_traces(endless_baseline(), unread_candidate())
    assert len(reads) == len(_PAIR_QUESTIONS) + 1


def test_run_trace_pairing_bounds_unending_candidate_after_valid_baseline():
    reads = []

    def endless_candidate():
        while True:
            reads.append(1)
            yield _paired_run_trace("a", "D6")

    baseline = [_paired_run_trace("a", "D3"), _paired_run_trace("b", "D3")]
    with pytest.raises(ValueError, match="candidate has more records"):
        _compare_paired_traces(iter(baseline), endless_candidate())
    assert len(reads) == len(_PAIR_QUESTIONS) + 1


def test_run_trace_pairing_rejects_bad_baseline_before_candidate_read():
    def unread_candidate():
        raise AssertionError("candidate arm read before baseline identity validation")
        yield None

    baseline = [
        replace(_paired_run_trace("a", "D3"), variant_id="D6"),
        _paired_run_trace("b", "D3"),
    ]
    with pytest.raises(ValueError, match="variant_id mismatch"):
        _compare_paired_traces(iter(baseline), unread_candidate())



# Prospective-only: bounded one-pass task-keyed numeric comparators. All data
# below are synthetic; none represent historical or human-evaluation scores.
@pytest.mark.parametrize(
    "comparator",
    [paired_metric_comparison_by_task, paired_bootstrap_confidence_interval_by_task],
)
def test_task_keyed_comparators_bound_unending_baseline_before_candidate(comparator):
    reads = {"baseline": 0, "candidate": 0}

    def baseline():
        index = 0
        while True:
            reads["baseline"] += 1
            yield (f"extra-{index}", 0.0)
            index += 1

    def candidate():
        reads["candidate"] += 1
        yield ("a", 1.0)

    with pytest.raises(ValueError, match="baseline task coverage mismatch"):
        comparator(baseline(), candidate(), expected_task_ids=["a", "b"])
    assert reads == {"baseline": 1, "candidate": 0}


@pytest.mark.parametrize(
    "comparator",
    [paired_metric_comparison_by_task, paired_bootstrap_confidence_interval_by_task],
)
def test_task_keyed_comparators_bound_unending_candidate_after_valid_baseline(
    comparator,
):
    reads = 0

    def candidate():
        nonlocal reads
        index = 0
        while True:
            reads += 1
            yield (f"extra-{index}", 1.0)
            index += 1

    with pytest.raises(ValueError, match="candidate task coverage mismatch"):
        comparator(
            [("a", 0.0), ("b", 0.0)],
            candidate(),
            expected_task_ids=["a", "b"],
        )
    assert reads == 1


@pytest.mark.parametrize(
    "comparator",
    [paired_metric_comparison_by_task, paired_bootstrap_confidence_interval_by_task],
)
@pytest.mark.parametrize("bad_arm", ["baseline", "candidate"])
def test_task_keyed_comparators_reject_first_unplanned_id_before_invalid_metric(
    comparator, bad_arm,
):
    """A substituted ID, not a later corrupt metric, is the first error."""
    reads = {"unexpected": 0, "opposite": 0}

    def substituted():
        reads["unexpected"] += 1
        yield ("unplanned-task", float("nan"))
        raise AssertionError("off-manifest stream must not advance past first record")

    def valid():
        reads["opposite"] += 1
        yield ("a", 0.0)
        yield ("b", 0.0)

    baseline, candidate = (
        (substituted(), valid()) if bad_arm == "baseline"
        else (valid(), substituted())
    )
    with pytest.raises(ValueError, match=f"{bad_arm} task coverage mismatch: unexpected"):
        comparator(baseline, candidate, expected_task_ids=["a", "b"])
    assert reads["unexpected"] == 1
    assert reads["opposite"] == (0 if bad_arm == "baseline" else 1)


def test_task_keyed_bootstrap_invalid_baseline_does_not_touch_candidate():
    def candidate():
        raise AssertionError("candidate must not be read on bad baseline")
        yield ("a", 1.0)

    with pytest.raises(ValueError, match="baseline task coverage mismatch"):
        paired_bootstrap_confidence_interval_by_task(
            [("a", 0.0)],
            candidate(),
            expected_task_ids=["a", "b"],
        )


def test_task_keyed_bootstrap_one_pass_compatibility_remains_seeded():
    def arm(rows):
        yield from rows

    params = dict(expected_task_ids=["a", "b"], seed=17, n_resamples=19)
    first = paired_bootstrap_confidence_interval_by_task(
        arm([("b", 0.5), ("a", 0.25)]),
        arm([("a", 0.5), ("b", 0.75)]),
        **params,
    )
    second = paired_bootstrap_confidence_interval_by_task(
        arm([("a", 0.25), ("b", 0.5)]),
        arm([("b", 0.75), ("a", 0.5)]),
        **params,
    )
    assert first == second
    assert first["mean_delta"] == 0.25
    assert first["bootstrap_confidence_interval"]["estimate"] == 0.25


# Prospective diagnostic reference preflight only. Synthetic, no provider calls.
def test_reference_manifest_at_explicit_limit_preserves_valid_one_pass_order():
    task_ids, questions = _validated_reference_task_manifest(
        (f"task-{index:05d}" for index in range(MAX_DIAGNOSTIC_REFERENCE_TASKS))
    )
    assert len(task_ids) == MAX_DIAGNOSTIC_REFERENCE_TASKS
    assert task_ids[0] == "task-00000"
    assert task_ids[-1] == f"task-{MAX_DIAGNOSTIC_REFERENCE_TASKS - 1:05d}"
    assert questions is None


@pytest.mark.parametrize(
    "comparator",
    [paired_metric_comparison_by_task, paired_bootstrap_confidence_interval_by_task],
)
def test_unbounded_independent_task_reference_fails_before_reading_arms(comparator):
    reference_reads = 0
    arm_reads = 0

    def infinite_unique_reference():
        nonlocal reference_reads
        index = 0
        while True:
            reference_reads += 1
            yield f"task-{index}"
            index += 1

    def forbidden_arm():
        nonlocal arm_reads
        arm_reads += 1
        raise AssertionError("invalid reference must not consume observations")
        yield ("task-0", 1.0)

    with pytest.raises(ValueError, match="diagnostic reference limit"):
        comparator(
            forbidden_arm(), forbidden_arm(),
            expected_task_ids=infinite_unique_reference(),
        )
    assert reference_reads == MAX_DIAGNOSTIC_REFERENCE_TASKS + 1
    assert arm_reads == 0


def test_unbounded_independent_question_mapping_fails_before_trace_reads():
    class UnboundedQuestions(dict):
        def __init__(self):
            self.reads = 0

        def items(self):
            index = 0
            while True:
                self.reads += 1
                yield f"unknown-{index}", "Synthetic question?"
                index += 1

    questions = UnboundedQuestions()
    observations = 0

    def forbidden_runs():
        nonlocal observations
        observations += 1
        raise AssertionError("invalid reference must not consume a trace")
        yield _task_aggregate_trace("task-a")

    with pytest.raises(ValueError, match="question coverage mismatch"):
        aggregate_runs_by_task(
            forbidden_runs(), variant_id="D3", task_set_id="frozen-diagnostic",
            expected_task_ids=["task-a"], expected_questions_by_task=questions,
        )
    assert questions.reads == 2
    assert observations == 0


def test_independent_question_mapping_still_accepts_complete_one_pass_reference():
    task_ids, questions = _validated_reference_task_manifest(
        (x for x in ["task-b", "task-a"]),
        {"task-b": "Question B?", "task-a": "Question A?"},
    )
    assert task_ids == ["task-a", "task-b"]
    assert questions == {"task-b": "Question B?", "task-a": "Question A?"}


# Independent planned settings are prospective diagnostic inputs, not observed data.
def test_unbounded_planned_fields_fail_at_seventh_entry_without_trace_reads():
    class InfiniteFields(dict):
        def __init__(self):
            self.reads = 0

        def items(self):
            for field, value in _PLANNED["D3"].items():
                self.reads += 1
                yield field, value
            index = 0
            while True:
                self.reads += 1
                yield f"extra-field-{index}", index
                index += 1

    plan = InfiniteFields()
    observed = 0

    def forbidden_runs():
        nonlocal observed
        observed += 1
        raise AssertionError("invalid plan cannot consume treatment records")
        yield _planned_trace("a", "D3")

    with pytest.raises(ValueError, match="expected_treatment_settings.*exactly six"):
        aggregate_runs_by_task(
            forbidden_runs(), variant_id="D3", task_set_id="prospective-paired",
            expected_task_ids=["a"], expected_treatment_settings=plan,
        )
    assert plan.reads == 7
    assert observed == 0


def test_unbounded_planned_variants_fail_at_third_entry_without_arm_reads():
    class InfiniteVariants(dict):
        def __init__(self):
            self.reads = 0

        def items(self):
            for variant, fields in _PLANNED.items():
                self.reads += 1
                yield variant, fields
            index = 0
            while True:
                self.reads += 1
                yield f"extra-variant-{index}", _PLANNED["D3"]
                index += 1

    plans = InfiniteVariants()
    observed = 0

    def forbidden_runs():
        nonlocal observed
        observed += 1
        raise AssertionError("invalid plan cannot consume either treatment arm")
        yield _planned_trace("a", "D3")

    with pytest.raises(ValueError, match="expected_treatment_settings_by_variant.*exactly both"):
        _compare_paired_traces(
            forbidden_runs(), forbidden_runs(),
            expected_treatment_settings_by_variant=plans,
        )
    assert plans.reads == 3
    assert observed == 0


def test_valid_one_pass_planned_mappings_preserve_seeded_paired_result():
    class OnePassMapping(dict):
        def __init__(self, source):
            super().__init__()
            self.source = source
            self.used = False

        def items(self):
            if self.used:
                raise AssertionError("planned source read more than once")
            self.used = True
            yield from self.source.items()

    baseline = [_planned_trace("a", "D3"), _planned_trace("b", "D3")]
    candidate = [_planned_trace("a", "D6"), _planned_trace("b", "D6")]
    control = _compare_paired_traces(
        baseline, candidate, expected_treatment_settings_by_variant=_PLANNED
    )
    nested = {variant: OnePassMapping(fields) for variant, fields in _PLANNED.items()}
    actual = _compare_paired_traces(
        iter(baseline), iter(candidate),
        expected_treatment_settings_by_variant=OnePassMapping(nested),
    )
    assert actual == control
