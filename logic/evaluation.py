"""Lightweight evaluation helpers for reproducible agent experiments.

The module is intentionally dependency-free so that run traces can be scored
without requiring an LLM provider or network access. It does not claim any
benchmark results; it only defines metrics and aggregation utilities.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor, isfinite, sqrt
from random import Random
from typing import Callable, Iterable, Sequence


@dataclass(frozen=True)
class RunTrace:
    """A normalized record for one research-agent run."""

    run_id: str
    completed: bool
    source_count: int
    failed_source_count: int = 0
    citation_count: int = 0
    unsupported_claim_count: int = 0
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: float = 0.0

    # Experimental metadata. Defaults preserve compatibility with older traces.
    variant_id: str = ""
    task_set_id: str = ""
    task_id: str = ""
    question: str = ""
    planning_mode: str = ""
    verification_mode: str = ""
    source_budget: int = 0
    query_count: int = 0
    search_call_count: int = 0
    model_call_count: int = 0
    unavailable_usage_call_count: int = 0
    supported_claim_count: int = 0
    partially_supported_claim_count: int = 0
    contradicted_claim_count: int = 0
    smart_model: str = ""
    fast_model: str = ""
    temperature: float = 0.0
    usage_accounting_status: str = "unavailable"
    cost_accounting_status: str = "not_computed"

    def __post_init__(self) -> None:
        """Reject impossible source, claim, and resource telemetry before scoring.

        Malformed counts or non-finite timing/cost values can poison bounded
        diagnostic rates and descriptive budget-efficiency aggregates.
        This is an in-memory diagnostic contract, not archival attestation.
        """
        if type(self.completed) is not bool:
            raise ValueError("completed must be a Boolean")
        count_fields = (
            "source_count",
            "failed_source_count",
            "citation_count",
            "supported_claim_count",
            "partially_supported_claim_count",
            "unsupported_claim_count",
            "contradicted_claim_count",
            "prompt_tokens",
            "completion_tokens",
            "source_budget",
            "query_count",
            "search_call_count",
            "model_call_count",
            "unavailable_usage_call_count",
        )
        for field in count_fields:
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field} must be a nonnegative integer")
        if self.failed_source_count > self.source_count:
            raise ValueError("failed_source_count cannot exceed source_count")
        if self.unavailable_usage_call_count > self.model_call_count:
            raise ValueError(
                "unavailable_usage_call_count cannot exceed model_call_count"
            )
        for field in ("latency_seconds", "estimated_cost_usd"):
            value = getattr(self, field)
            if type(value) not in (int, float):
                raise ValueError(f"{field} must be a finite nonnegative number")
            try:
                finite = isfinite(value)
            except OverflowError:
                finite = False
            if not finite or value < 0:
                raise ValueError(f"{field} must be a finite nonnegative number")

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def successful_source_count(self) -> int:
        return self.source_count - self.failed_source_count

    @property
    def source_success_rate(self) -> float:
        if self.source_count <= 0:
            return 0.0
        return self.successful_source_count / self.source_count

    @property
    def verified_claim_count(self) -> int:
        explicit_total = (
            self.supported_claim_count
            + self.partially_supported_claim_count
            + self.unsupported_claim_count
            + self.contradicted_claim_count
        )
        return explicit_total if explicit_total > 0 else self.citation_count

    @property
    def claim_support_rate(self) -> float:
        """Strict support rate: fully supported claims / all verified claims."""
        total = self.verified_claim_count
        if total <= 0:
            return 0.0
        return self.supported_claim_count / total

    @property
    def citation_precision_proxy(self) -> float:
        """Legacy conservative proxy based on manually flagged unsupported claims."""
        if self.citation_count <= 0:
            return 0.0
        supported = max(self.citation_count - self.unsupported_claim_count, 0)
        return supported / self.citation_count

    def to_dict(self) -> dict:
        data = asdict(self)
        data["total_tokens"] = self.total_tokens
        data["successful_source_count"] = self.successful_source_count
        data["source_success_rate"] = self.source_success_rate
        data["verified_claim_count"] = self.verified_claim_count
        data["claim_support_rate"] = self.claim_support_rate
        data["citation_precision_proxy"] = self.citation_precision_proxy
        return data


def safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def safe_median(values: Iterable[float]) -> float:
    """Return the median, or 0.0 for an empty iterable."""
    ordered = sorted(values)
    size = len(ordered)
    if size == 0:
        return 0.0
    midpoint = size // 2
    if size % 2:
        return float(ordered[midpoint])
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def population_stddev(values: Iterable[float]) -> float:
    """Return population standard deviation, defined as 0.0 when empty."""
    values = list(values)
    if not values:
        return 0.0
    mean = safe_mean(values)
    return sqrt(safe_mean((value - mean) ** 2 for value in values))


def _finite_float(value: float, *, label: str) -> float:
    """Normalize one numeric value and reject invalid statistical inputs."""
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not isfinite(normalized):
        raise ValueError(f"{label} must be finite")
    return normalized


def _finite_values(values: Iterable[float], *, label: str) -> list[float]:
    return [_finite_float(value, label=label) for value in values]


def _linear_quantile(ordered: Sequence[float], probability: float) -> float:
    """Return the linearly interpolated quantile of a sorted sample."""
    position = probability * (len(ordered) - 1)
    lower_index = floor(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return float(
        (1.0 - fraction) * ordered[lower_index]
        + fraction * ordered[upper_index]
    )


def bootstrap_confidence_interval(
    values: Sequence[float],
    statistic: Callable[[Iterable[float]], float] = safe_mean,
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
) -> dict:
    """Return a reproducible percentile-bootstrap interval for a statistic.

    A local seeded RNG keeps reports reproducible without mutating global random
    state. The returned interval is descriptive uncertainty and does not imply
    statistical significance.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")

    sample = _finite_values(values, label="bootstrap sample")
    if not sample:
        return {
            "estimate": 0.0,
            "lower": 0.0,
            "upper": 0.0,
            "confidence": confidence,
            "n_resamples": n_resamples,
        }

    rng = Random(seed)
    estimates = sorted(
        _finite_float(
            statistic(rng.choices(sample, k=len(sample))),
            label="bootstrap statistic",
        )
        for _ in range(n_resamples)
    )
    estimate = _finite_float(statistic(sample), label="bootstrap statistic")
    alpha = (1.0 - confidence) / 2.0
    lower = _finite_float(
        _linear_quantile(estimates, alpha), label="bootstrap interval"
    )
    upper = _finite_float(
        _linear_quantile(estimates, 1.0 - alpha), label="bootstrap interval"
    )
    return {
        "estimate": estimate,
        "lower": lower,
        "upper": upper,
        "confidence": confidence,
        "n_resamples": n_resamples,
    }


def paired_metric_comparison(
    baseline: Sequence[float], candidate: Sequence[float]
) -> dict:
    """Summarize per-task deltas for two variants evaluated on the same tasks.

    Values must be aligned by task and use a metric where larger is better.
    Keeping the comparison paired prevents task difficulty from being hidden by
    comparing two unrelated aggregate means. Statistical significance is not
    inferred here; the returned dispersion and win/tie/loss counts are
    descriptive evidence only.
    """
    if len(baseline) != len(candidate):
        raise ValueError("paired comparisons require equal-length sequences")

    baseline_values = _finite_values(baseline, label="baseline values")
    candidate_values = _finite_values(candidate, label="candidate values")
    deltas = [
        _finite_float(new - old, label="paired deltas")
        for old, new in zip(baseline_values, candidate_values)
    ]
    try:
        mean_delta = safe_mean(deltas)
        median_delta = safe_median(deltas)
        delta_stddev = population_stddev(deltas)
    except OverflowError as exc:
        raise ValueError("paired summary must be finite") from exc

    return {
        "n_pairs": len(deltas),
        "mean_delta": _finite_float(mean_delta, label="paired summary"),
        "median_delta": _finite_float(median_delta, label="paired summary"),
        "delta_stddev": _finite_float(delta_stddev, label="paired summary"),
        "wins": sum(delta > 0 for delta in deltas),
        "ties": sum(delta == 0 for delta in deltas),
        "losses": sum(delta < 0 for delta in deltas),
    }


def paired_metric_comparison_by_task(
    baseline: Iterable[tuple[str, float]],
    candidate: Iterable[tuple[str, float]],
    *,
    expected_task_ids: Iterable[str],
) -> dict:
    """Descriptively compare complete, explicitly task-keyed metric records.

    Unlike positional pairing, this refuses duplicate IDs, cross-arm task
    substitution, and jointly omitted tasks relative to the caller's
    independently defined expected set. Sorting the validated keys makes
    floating-point accumulation reproducible under record reordering.

    This is a diagnostic helper, not the frozen main-study inference path.
    Its coverage check is only as trustworthy as the provided task manifest.
    """
    def valid_id(value: str, label: str) -> str:
        if type(value) is not str or not value or value.strip() != value:
            raise ValueError(f"{label} task_id must be a nonempty, unpadded string")
        return value

    expected: set[str] = set()
    for task_id in expected_task_ids:
        task_id = valid_id(task_id, "expected")
        if task_id in expected:
            raise ValueError(f"duplicate expected task_id: {task_id!r}")
        expected.add(task_id)
    if not expected:
        raise ValueError("expected_task_ids must not be empty")

    def index_records(
        records: Iterable[tuple[str, float]], label: str
    ) -> dict[str, float]:
        indexed: dict[str, float] = {}
        for record in records:
            if not isinstance(record, (tuple, list)) or len(record) != 2:
                raise ValueError(f"{label} records must be (task_id, metric) pairs")
            task_id, value = record
            task_id = valid_id(task_id, label)
            if task_id in indexed:
                raise ValueError(f"duplicate {label} task_id: {task_id!r}")
            if type(value) not in (int, float):
                raise ValueError(f"{label} metric must be a finite number")
            try:
                indexed[task_id] = _finite_float(
                    value, label=f"{label} metric"
                )
            except OverflowError as exc:
                raise ValueError(f"{label} metric must be a finite number") from exc
        missing = sorted(expected - indexed.keys())
        unexpected = sorted(indexed.keys() - expected)
        if missing or unexpected:
            raise ValueError(
                f"{label} task coverage mismatch: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
        return indexed

    baseline_by_task = index_records(baseline, "baseline")
    candidate_by_task = index_records(candidate, "candidate")
    task_ids = sorted(expected)
    result = paired_metric_comparison(
        [baseline_by_task[task_id] for task_id in task_ids],
        [candidate_by_task[task_id] for task_id in task_ids],
    )
    return {"task_ids": task_ids, **result}


def aggregate_runs(runs: Sequence[RunTrace]) -> dict:
    """Aggregate run-level traces into experiment-level summary metrics.

    Means remain available for backwards compatibility. Median latency/cost
    and dispersion metrics make comparisons less sensitive to occasional
    network/model outliers and expose run-to-run instability explicitly.
    """
    if not runs:
        return {
            "n_runs": 0,
            "completion_rate": 0.0,
            "avg_sources": 0.0,
            "avg_successful_sources": 0.0,
            "avg_source_success_rate": 0.0,
            "avg_claim_support_rate": 0.0,
            "avg_citation_precision_proxy": 0.0,
            "avg_latency_seconds": 0.0,
            "median_latency_seconds": 0.0,
            "latency_stddev_seconds": 0.0,
            "avg_total_tokens": 0.0,
            "avg_model_calls": 0.0,
            "avg_search_calls": 0.0,
            "total_tokens_stddev": 0.0,
            "avg_estimated_cost_usd": 0.0,
            "median_estimated_cost_usd": 0.0,
        }

    try:
        latencies = [run.latency_seconds for run in runs]
        total_tokens = [float(run.total_tokens) for run in runs]
        costs = [run.estimated_cost_usd for run in runs]

        summary = {
            "n_runs": len(runs),
            "completion_rate": safe_mean(1.0 if run.completed else 0.0 for run in runs),
            "avg_sources": safe_mean(float(run.source_count) for run in runs),
            "avg_successful_sources": safe_mean(
                float(run.successful_source_count) for run in runs
            ),
            "avg_source_success_rate": safe_mean(run.source_success_rate for run in runs),
            "avg_claim_support_rate": safe_mean(run.claim_support_rate for run in runs),
            "avg_citation_precision_proxy": safe_mean(
                run.citation_precision_proxy for run in runs
            ),
            "avg_latency_seconds": safe_mean(latencies),
            "median_latency_seconds": safe_median(latencies),
            "latency_stddev_seconds": population_stddev(latencies),
            "avg_total_tokens": safe_mean(total_tokens),
            "total_tokens_stddev": population_stddev(total_tokens),
            "avg_model_calls": safe_mean(float(run.model_call_count) for run in runs),
            "avg_search_calls": safe_mean(float(run.search_call_count) for run in runs),
            "avg_estimated_cost_usd": safe_mean(costs),
            "median_estimated_cost_usd": safe_median(costs),
        }

    except OverflowError as exc:
        raise ValueError("aggregate run statistics must be finite") from exc
    for metric, value in summary.items():
        if metric != "n_runs" and not isfinite(value):
            raise ValueError(f"{metric} must be finite")
    return summary


def aggregate_runs_by_task(
    runs: Iterable[RunTrace],
    *,
    variant_id: str,
    task_set_id: str,
    expected_task_ids: Iterable[str],
) -> dict:
    """Aggregate one complete diagnostic treatment arm against a task manifest.

    Caller-supplied task/variant identity is an independent coverage contract,
    not a claim that the historical source files or manifest are authenticated.
    Unlike generic aggregate_runs, this opt-in helper rejects dropped tasks,
    duplicate attempts, run-ID reuse, and accidental cross-arm pooling. Failed
    runs remain in the denominator. Sorting by task ID makes sums reproducible
    if input records arrive in different orders.

    This does not change the separately frozen main-study analysis.
    """
    def valid_identifier(value: str, label: str) -> str:
        if (
            type(value) is not str
            or not value
            or not value.strip()
            or value.strip() != value
        ):
            raise ValueError(f"{label} must be a nonempty, unpadded string")
        return value

    variant_id = valid_identifier(variant_id, "variant_id")
    task_set_id = valid_identifier(task_set_id, "task_set_id")

    expected: set[str] = set()
    for task_id in expected_task_ids:
        task_id = valid_identifier(task_id, "expected task_id")
        if task_id in expected:
            raise ValueError(f"duplicate expected task_id: {task_id!r}")
        expected.add(task_id)
    if not expected:
        raise ValueError("expected_task_ids must not be empty")

    by_task: dict[str, RunTrace] = {}
    seen_run_ids: set[str] = set()
    for trace in runs:
        if not isinstance(trace, RunTrace):
            raise ValueError("runs must contain RunTrace records")
        task_id = valid_identifier(trace.task_id, "observed task_id")
        run_id = valid_identifier(trace.run_id, "run_id")
        if type(trace.completed) is not bool:
            raise ValueError("completed must be a Boolean")
        if trace.variant_id != variant_id:
            raise ValueError(f"variant_id mismatch for task {task_id!r}")
        if trace.task_set_id != task_set_id:
            raise ValueError(f"task_set_id mismatch for task {task_id!r}")
        if task_id in by_task:
            raise ValueError(f"duplicate observed task_id: {task_id!r}")
        if run_id in seen_run_ids:
            raise ValueError(f"duplicate run_id: {run_id!r}")
        by_task[task_id] = trace
        seen_run_ids.add(run_id)

    missing = sorted(expected - by_task.keys())
    unexpected = sorted(by_task.keys() - expected)
    if missing or unexpected:
        raise ValueError(
            f"task coverage mismatch: missing={missing!r}, unexpected={unexpected!r}"
        )

    task_ids = sorted(expected)
    summary = aggregate_runs([by_task[task_id] for task_id in task_ids])
    return {
        "variant_id": variant_id,
        "task_set_id": task_set_id,
        "task_ids": task_ids,
        **summary,
    }


def deduplicate_sources(urls: Iterable[str]) -> list[str]:
    """Return normalized, order-preserving unique source URLs."""
    seen: set[str] = set()
    unique: list[str] = []

    for raw_url in urls:
        url = (raw_url or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        unique.append(url)

    return unique
