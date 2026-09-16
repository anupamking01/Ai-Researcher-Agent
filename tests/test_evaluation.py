import pytest

from logic.evaluation import (
    RunTrace,
    aggregate_runs,
    deduplicate_sources,
    population_stddev,
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


def test_aggregate_runs():
    runs = [
        RunTrace(
            run_id="run-1",
            completed=True,
            source_count=10,
            failed_source_count=2,
            latency_seconds=20.0,
            prompt_tokens=100,
            completion_tokens=50,
            estimated_cost_usd=0.05,
        ),
        RunTrace(
            run_id="run-2",
            completed=False,
            source_count=5,
            failed_source_count=5,
            latency_seconds=10.0,
            prompt_tokens=50,
            completion_tokens=25,
            estimated_cost_usd=0.02,
        ),
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


def test_deduplicate_sources_preserves_order():
    urls = [
        " https://example.com/a ",
        "https://example.com/b",
        "https://example.com/a",
        "",
        "https://example.com/c",
    ]

    assert deduplicate_sources(urls) == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]
