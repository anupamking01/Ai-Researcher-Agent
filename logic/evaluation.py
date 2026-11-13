"""Lightweight evaluation helpers for reproducible agent experiments.

The module is intentionally dependency-free so that run traces can be scored
without requiring an LLM provider or network access. It does not claim any
benchmark results; it only defines metrics and aggregation utilities.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from math import floor, fsum, isfinite, sqrt
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
        for field in ("latency_seconds", "estimated_cost_usd", "temperature"):
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
    """Return a mean without overflowing an otherwise representable center.

    Prefer accurate full-scale summation (including tiny subnormal values).
    If that sum overflows, divide each term by the sample count before
    accumulating: a finite sample of finite floats has a finite mean.
    """
    values = list(values)
    if not values:
        return 0.0
    count = len(values)
    try:
        return fsum(values) / count
    except OverflowError:
        return fsum(value / count for value in values)


def safe_median(values: Iterable[float]) -> float:
    """Return the median, or 0.0 for an empty iterable."""
    ordered = sorted(values)
    size = len(ordered)
    if size == 0:
        return 0.0
    midpoint = size // 2
    if size % 2:
        return float(ordered[midpoint])
    left, right = ordered[midpoint - 1], ordered[midpoint]
    midpoint_sum = left + right
    if isfinite(midpoint_sum):
        return midpoint_sum / 2
    # The same-sign intermediate sum overflowed, not the finite midpoint.
    # Use halves only in that case to preserve subnormal input precision.
    return left / 2 + right / 2


def population_stddev(values: Iterable[float]) -> float:
    """Return population stddev without overflowing squared finite deviations.

    Center and square dimensionless observations, then restore their scale.
    For instance, [0, 1e200] has representable stddev 5e199 even though
    squaring an unscaled 5e199 deviation would overflow binary64.
    """
    values = list(values)
    if not values:
        return 0.0
    scale = max(abs(value) for value in values)
    if scale == 0:
        return 0.0
    normalized = [value / scale for value in values]
    mean = safe_mean(normalized)
    return scale * sqrt(
        safe_mean((value - mean) ** 2 for value in normalized)
    )


def _finite_float(value: float, *, label: str) -> float:
    """Require finite numeric observations, never coerced text or Booleans.

    This shared boundary protects raw positional pairing, bootstrap samples,
    and user-supplied bootstrap statistics. It matches the stricter task-keyed
    metric contract without changing numerical estimators.
    """
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be finite")
    try:
        normalized = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
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
    left, right = ordered[lower_index], ordered[upper_index]
    # A weighted sum can erase constant subnormal observations: 0.5 times
    # the smallest float rounds to zero, collapsing a nonzero percentile.
    if left == right:
        return float(left)
    # For same-sign endpoints, the span is finite and interpolation retains
    # small endpoints without independently rounding both weighted terms.
    if left >= 0 or right <= 0:
        return float(left + fraction * (right - left))
    # Opposite-sign endpoints may have an unrepresentable difference even
    # though their interpolated percentile is finite.
    return float((1.0 - fraction) * left + fraction * right)


def _validate_bootstrap_settings(
    confidence: float, n_resamples: int, seed: int
) -> None:
    """Reject ambiguous bootstrap parameters before consuming any observations.

    In particular, a single draw cannot define percentile uncertainty, and
    Boolean or coerced text parameters are not explicit experiment settings.
    This is a diagnostic input contract, not a change to the estimator.
    """
    if type(confidence) not in (int, float) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be a finite number between 0 and 1")
    if type(n_resamples) is not int or n_resamples < 2:
        raise ValueError("n_resamples must be an integer >= 2")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")


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
    _validate_bootstrap_settings(confidence, n_resamples, seed)

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


def _validated_reference_task_manifest(
    expected_task_ids: Iterable[str],
    expected_questions_by_task: Mapping[str, str] | None = None,
) -> tuple[list[str], dict[str, str] | None]:
    """Snapshot an independent reference before consuming observed results.

    A scalar string is *not* a task collection: silently iterating its
    characters could make a malformed one-task manifest appear complete.
    Validate the full ID/question contract first, including on one-pass
    reference iterators, so neither treatment arm is read on invalid input.
    """
    if isinstance(expected_task_ids, (str, bytes)):
        raise ValueError("expected_task_ids must be a collection, not scalar text")
    expected: set[str] = set()
    for task_id in expected_task_ids:
        if (
            type(task_id) is not str or not task_id
            or task_id.strip() != task_id or not task_id.strip()
        ):
            raise ValueError("expected task_id must be a nonempty, unpadded string")
        if task_id in expected:
            raise ValueError(f"duplicate expected task_id: {task_id!r}")
        expected.add(task_id)
    if not expected:
        raise ValueError("expected_task_ids must not be empty")

    questions_by_task: dict[str, str] | None = None
    if expected_questions_by_task is not None:
        if not isinstance(expected_questions_by_task, Mapping):
            raise ValueError("expected_questions_by_task must be a mapping")
        questions_by_task = {}
        for task_id, question in expected_questions_by_task.items():
            if (
                type(task_id) is not str or not task_id
                or task_id.strip() != task_id or not task_id.strip()
            ):
                raise ValueError(
                    "expected question task_id must be a nonempty, unpadded string"
                )
            if type(question) is not str or not question.strip():
                raise ValueError("expected task question must be nonempty text")
            questions_by_task[task_id] = question
        missing_questions = sorted(expected - questions_by_task.keys())
        unexpected_questions = sorted(questions_by_task.keys() - expected)
        if missing_questions or unexpected_questions:
            raise ValueError(
                "expected task question coverage mismatch: "
                f"missing={missing_questions!r}, "
                f"unexpected={unexpected_questions!r}"
            )
    return sorted(expected), questions_by_task


def _index_complete_task_metrics(
    records: Iterable[tuple[str, float]],
    *,
    label: str,
    expected_task_ids: set[str],
) -> dict[str, float]:
    """Validate one one-pass task arm with bounded memory and early failure.

    No stream can contribute more unique records than the independent frozen
    reference. A duplicate fails immediately; an extra distinct record fails
    on the first excess observation instead of exhausting an unbounded source.
    """
    indexed: dict[str, float] = {}
    for record in records:
        if not isinstance(record, (tuple, list)) or len(record) != 2:
            raise ValueError(f"{label} records must be (task_id, metric) pairs")
        task_id, value = record
        if type(task_id) is not str or not task_id or task_id.strip() != task_id:
            raise ValueError(f"{label} task_id must be a nonempty, unpadded string")
        if task_id in indexed:
            raise ValueError(f"duplicate {label} task_id: {task_id!r}")
        if type(value) not in (int, float):
            raise ValueError(f"{label} metric must be a finite number")
        indexed[task_id] = _finite_float(value, label=f"{label} metric")
        if len(indexed) > len(expected_task_ids):
            missing = sorted(expected_task_ids - indexed.keys())
            unexpected = sorted(indexed.keys() - expected_task_ids)
            raise ValueError(
                f"{label} task coverage mismatch: "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )
    missing = sorted(expected_task_ids - indexed.keys())
    unexpected = sorted(indexed.keys() - expected_task_ids)
    if missing or unexpected:
        raise ValueError(
            f"{label} task coverage mismatch: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )
    return indexed


def paired_metric_comparison_by_task(
    baseline: Iterable[tuple[str, float]],
    candidate: Iterable[tuple[str, float]],
    *,
    expected_task_ids: Iterable[str],
) -> dict:
    """Descriptively compare task-keyed numeric metrics with complete coverage.

    Validate each arm against an independent reference before reading the next
    arm, including on one-pass or unbounded sources. Sorting task IDs preserves
    deterministic accumulation. This remains prospective diagnostic analysis.
    """
    task_ids, _ = _validated_reference_task_manifest(expected_task_ids)
    expected = set(task_ids)
    baseline_by_task = _index_complete_task_metrics(
        baseline, label="baseline", expected_task_ids=expected
    )
    candidate_by_task = _index_complete_task_metrics(
        candidate, label="candidate", expected_task_ids=expected
    )
    result = paired_metric_comparison(
        [baseline_by_task[task_id] for task_id in task_ids],
        [candidate_by_task[task_id] for task_id in task_ids],
    )
    return {"task_ids": task_ids, **result}


def paired_bootstrap_confidence_interval_by_task(
    baseline: Iterable[tuple[str, float]],
    candidate: Iterable[tuple[str, float]],
    *,
    expected_task_ids: Iterable[str],
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
) -> dict:
    """Bootstrap complete, task-matched candidate-minus-baseline differences.

    Validate both arms against an independent expected task set *before*
    drawing any samples. Re-sample the paired differences, never the arms
    independently, and sort task IDs so input ordering cannot change seeded
    resampling. This prospective diagnostic interval is descriptive only;
    it does not replace the separately frozen main-study inference.
    """
    _validate_bootstrap_settings(confidence, n_resamples, seed)
    task_ids, _ = _validated_reference_task_manifest(expected_task_ids)

    # Index one arm at a time against the independent reference. This
    # prevents unbounded list(...) reads and rejects a malformed baseline
    # before consuming any candidate records. One-pass iterators stay valid.
    expected = set(task_ids)
    baseline_by_task = _index_complete_task_metrics(
        baseline, label="baseline", expected_task_ids=expected
    )
    candidate_by_task = _index_complete_task_metrics(
        candidate, label="candidate", expected_task_ids=expected
    )
    comparison = paired_metric_comparison(
        [baseline_by_task[task_id] for task_id in task_ids],
        [candidate_by_task[task_id] for task_id in task_ids],
    )
    differences = [
        _finite_float(
            candidate_by_task[task_id] - baseline_by_task[task_id],
            label="paired deltas",
        )
        for task_id in task_ids
    ]
    interval = bootstrap_confidence_interval(
        differences,
        statistic=safe_mean,
        confidence=confidence,
        n_resamples=n_resamples,
        seed=seed,
    )
    return {
        "task_ids": task_ids,
        **comparison,
        "bootstrap_method": "paired_percentile_mean_delta",
        "bootstrap_confidence_interval": interval,
    }


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


_TREATMENT_FIELDS = (
    "planning_mode", "verification_mode", "source_budget",
    "smart_model", "fast_model", "temperature",
)


def _validated_treatment_settings(settings: Mapping[str, object]) -> dict[str, object]:
    """Capture the independently planned treatment settings before trace reads."""
    if not isinstance(settings, Mapping):
        raise ValueError("expected_treatment_settings must be a mapping")
    planned = dict(settings.items())
    if set(planned) != set(_TREATMENT_FIELDS):
        raise ValueError("expected_treatment_settings must declare exactly six fields")
    for field in ("planning_mode", "verification_mode", "smart_model", "fast_model"):
        value = planned[field]
        if (
            type(value) is not str
            or value != value.strip()
            or (field in ("planning_mode", "verification_mode") and not value)
        ):
            raise ValueError(f"expected_treatment_settings {field} must be valid text")
    budget = planned["source_budget"]
    if type(budget) is not int or budget < 0:
        raise ValueError("expected_treatment_settings source_budget must be nonnegative int")
    temperature = _finite_float(
        planned["temperature"], label="expected_treatment_settings temperature"
    )
    if temperature < 0:
        raise ValueError("expected_treatment_settings temperature must be nonnegative")
    planned["temperature"] = temperature
    return planned


def aggregate_runs_by_task(
    runs: Iterable[RunTrace],
    *,
    variant_id: str,
    task_set_id: str,
    expected_task_ids: Iterable[str],
    expected_questions_by_task: Mapping[str, str] | None = None,
    expected_treatment_settings: Mapping[str, object] | None = None,
) -> dict:
    """Aggregate one complete diagnostic treatment arm against a task manifest.

    Caller-supplied task/variant identity is an independent coverage contract,
    not a claim that the historical source files or manifest are authenticated.
    Unlike generic aggregate_runs, this opt-in helper rejects dropped tasks,
    duplicate attempts, run-ID reuse, and accidental cross-arm pooling. Failed
    runs remain in the denominator. Sorting by task ID makes sums reproducible
    if input records arrive in different orders. An optional independently
    sourced task-ID-to-question mapping rejects traces mislabeled with the
    correct task ID but the wrong research question, including cross-task
    question swaps that task-ID coverage alone cannot detect. An optional
    independently planned six-field configuration also detects mislabeled
    treatment settings despite otherwise valid task and variant IDs.

    This does not authenticate the provided manifest or the trace's original
    source bytes, or change the separately frozen main-study analysis.
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

    task_ids, questions_by_task = _validated_reference_task_manifest(
        expected_task_ids, expected_questions_by_task
    )
    expected = set(task_ids)

    expected_config = (
        _validated_treatment_settings(expected_treatment_settings)
        if expected_treatment_settings is not None else None
    )
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
        if expected_config is not None:
            for field, planned_value in expected_config.items():
                if getattr(trace, field) != planned_value:
                    raise ValueError(
                        f"treatment setting mismatch for {field} at task {task_id!r}"
                    )
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

    if questions_by_task is not None:
        for task_id in task_ids:
            observed_question = by_task[task_id].question
            if (
                type(observed_question) is not str
                or observed_question != questions_by_task[task_id]
            ):
                raise ValueError(
                    f"task question mismatch for task {task_id!r}"
                )
    summary = aggregate_runs([by_task[task_id] for task_id in task_ids])
    return {
        "variant_id": variant_id,
        "task_set_id": task_set_id,
        "task_ids": task_ids,
        **summary,
    }



def paired_run_trace_bootstrap_by_task(
    baseline_runs: Iterable[RunTrace],
    candidate_runs: Iterable[RunTrace],
    *,
    baseline_variant_id: str,
    candidate_variant_id: str,
    task_set_id: str,
    expected_task_ids: Iterable[str],
    expected_questions_by_task: Mapping[str, str],
    expected_treatment_settings_by_variant: (
        Mapping[str, Mapping[str, object]] | None
    ) = None,
    metric: str = "claim_support_rate",
    confidence: float = 0.95,
    n_resamples: int = 2000,
    seed: int = 0,
) -> dict:
    """Compare complete, independently identified diagnostic treatment arms.

    The lower-level task-keyed bootstrap accepts numeric observations without
    their treatment metadata. This adapter validates each RunTrace arm against
    independent task/question and optional planned treatment-setting manifests,
    rejects shared run IDs across arms,
    and only then extracts a preselected higher-is-better diagnostic rate.
    It neither authenticates historical source files nor replaces frozen
    main-study inference, whose inputs and procedure are separate.
    """
    _validate_bootstrap_settings(confidence, n_resamples, seed)
    if type(metric) is not str or metric not in (
        "claim_support_rate",
        "source_success_rate",
        "citation_precision_proxy",
    ):
        raise ValueError("metric must be a supported higher-is-better diagnostic rate")
    if baseline_variant_id == candidate_variant_id:
        raise ValueError("baseline and candidate variant IDs must differ")
    if not isinstance(expected_questions_by_task, Mapping):
        raise ValueError("expected_questions_by_task must be a mapping")

    configs = None
    if expected_treatment_settings_by_variant is not None:
        if not isinstance(expected_treatment_settings_by_variant, Mapping):
            raise ValueError("expected_treatment_settings_by_variant must be a mapping")
        raw_configs = dict(expected_treatment_settings_by_variant.items())
        if (
            type(baseline_variant_id) is not str
            or type(candidate_variant_id) is not str
            or set(raw_configs) != {baseline_variant_id, candidate_variant_id}
        ):
            raise ValueError(
                "expected_treatment_settings_by_variant must cover exactly both variants"
            )
        # Validate both independent plans before consuming any observed trace.
        configs = {
            variant: _validated_treatment_settings(raw_configs[variant])
            for variant in (baseline_variant_id, candidate_variant_id)
        }

    # Snapshot the independent reference once, including one-pass task IDs;
    # do not infer either expected set or questions from the observed arms.
    task_ids, questions = _validated_reference_task_manifest(
        expected_task_ids, expected_questions_by_task
    )
    # The independent reference bounds cardinality *before* we materialize
    # either one-pass arm. A never-ending or excessively repeated producer must
    # not exhaust memory while we are still checking the treatment matrix.
    def snapshot_arm(records: Iterable[RunTrace], label: str) -> list[RunTrace]:
        observed: list[RunTrace] = []
        for trace in records:
            if len(observed) >= len(task_ids):
                raise ValueError(
                    f"{label} has more records than the independent task manifest"
                )
            observed.append(trace)
        return observed

    baseline = snapshot_arm(baseline_runs, "baseline")
    # Check the first arm before touching the second arm. This prevents an
    # invalid baseline from exhausting a candidate generator or obscuring its
    # own provenance failure with a later unrelated producer error.
    aggregate_runs_by_task(
        baseline,
        variant_id=baseline_variant_id,
        task_set_id=task_set_id,
        expected_task_ids=task_ids,
        expected_questions_by_task=questions,
        expected_treatment_settings=(
            configs[baseline_variant_id] if configs is not None else None
        ),
    )
    candidate = snapshot_arm(candidate_runs, "candidate")
    aggregate_runs_by_task(
        candidate,
        variant_id=candidate_variant_id,
        task_set_id=task_set_id,
        expected_task_ids=task_ids,
        expected_questions_by_task=questions,
        expected_treatment_settings=(
            configs[candidate_variant_id] if configs is not None else None
        ),
    )
    reused_run_ids = sorted(
        {trace.run_id for trace in baseline}
        & {trace.run_id for trace in candidate}
    )
    if reused_run_ids:
        raise ValueError(
            f"run_id reused across baseline and candidate arms: {reused_run_ids!r}"
        )

    paired = paired_bootstrap_confidence_interval_by_task(
        ((trace.task_id, getattr(trace, metric)) for trace in baseline),
        ((trace.task_id, getattr(trace, metric)) for trace in candidate),
        expected_task_ids=task_ids,
        confidence=confidence,
        n_resamples=n_resamples,
        seed=seed,
    )
    return {
        "baseline_variant_id": baseline_variant_id,
        "candidate_variant_id": candidate_variant_id,
        "task_set_id": task_set_id,
        "metric": metric,
        **paired,
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
