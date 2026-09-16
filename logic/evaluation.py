"""Lightweight evaluation helpers for reproducible agent experiments.

The module is intentionally dependency-free so that run traces can be scored
without requiring an LLM provider or network access. It does not claim any
benchmark results; it only defines metrics and aggregation utilities.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from typing import Iterable, Sequence


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

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def source_success_rate(self) -> float:
        if self.source_count <= 0:
            return 0.0
        successful = max(self.source_count - self.failed_source_count, 0)
        return successful / self.source_count

    @property
    def citation_precision_proxy(self) -> float:
        """A conservative proxy based on manually flagged unsupported claims.

        This is not a factuality score. It only becomes meaningful when an
        evaluator has annotated unsupported claims using a fixed protocol.
        """
        if self.citation_count <= 0:
            return 0.0
        supported = max(self.citation_count - self.unsupported_claim_count, 0)
        return supported / self.citation_count

    def to_dict(self) -> dict:
        data = asdict(self)
        data["total_tokens"] = self.total_tokens
        data["source_success_rate"] = self.source_success_rate
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
            "avg_source_success_rate": 0.0,
            "avg_citation_precision_proxy": 0.0,
            "avg_latency_seconds": 0.0,
            "median_latency_seconds": 0.0,
            "latency_stddev_seconds": 0.0,
            "avg_total_tokens": 0.0,
            "total_tokens_stddev": 0.0,
            "avg_estimated_cost_usd": 0.0,
            "median_estimated_cost_usd": 0.0,
        }

    latencies = [run.latency_seconds for run in runs]
    total_tokens = [float(run.total_tokens) for run in runs]
    costs = [run.estimated_cost_usd for run in runs]

    return {
        "n_runs": len(runs),
        "completion_rate": safe_mean(1.0 if run.completed else 0.0 for run in runs),
        "avg_sources": safe_mean(float(run.source_count) for run in runs),
        "avg_source_success_rate": safe_mean(run.source_success_rate for run in runs),
        "avg_citation_precision_proxy": safe_mean(
            run.citation_precision_proxy for run in runs
        ),
        "avg_latency_seconds": safe_mean(latencies),
        "median_latency_seconds": safe_median(latencies),
        "latency_stddev_seconds": population_stddev(latencies),
        "avg_total_tokens": safe_mean(total_tokens),
        "total_tokens_stddev": population_stddev(total_tokens),
        "avg_estimated_cost_usd": safe_mean(costs),
        "median_estimated_cost_usd": safe_median(costs),
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
