"""Lightweight evaluation helpers for reproducible agent experiments."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import sqrt
from random import Random
from typing import Callable, Iterable, Sequence

@dataclass(frozen=True)
class RunTrace:
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
        return max(self.source_count - self.failed_source_count, 0) / self.source_count

    @property
    def citation_precision_proxy(self) -> float:
        """Conservative proxy based on manually flagged unsupported claims."""
        if self.citation_count <= 0:
            return 0.0
        return max(self.citation_count - self.unsupported_claim_count, 0) / self.citation_count

    def to_dict(self) -> dict:
        data = asdict(self)
        data.update(total_tokens=self.total_tokens, source_success_rate=self.source_success_rate,
                    citation_precision_proxy=self.citation_precision_proxy)
        return data

def safe_mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0

def safe_median(values: Iterable[float]) -> float:
    ordered = sorted(values)
    size = len(ordered)
    if not size:
        return 0.0
    midpoint = size // 2
    return float(ordered[midpoint]) if size % 2 else (ordered[midpoint - 1] + ordered[midpoint]) / 2

def population_stddev(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    mean = safe_mean(values)
    return sqrt(safe_mean((value - mean) ** 2 for value in values))

def bootstrap_confidence_interval(values: Sequence[float], statistic: Callable[[Iterable[float]], float] = safe_mean,
                                  confidence: float = 0.95, n_resamples: int = 2000, seed: int = 0) -> dict:
    """Return a deterministic percentile bootstrap interval for a statistic.

    The fixed seed makes evaluation reports reproducible. The interval is
    descriptive uncertainty, not evidence of statistical significance.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive")
    sample = [float(value) for value in values]
    if not sample:
        return {"estimate": 0.0, "lower": 0.0, "upper": 0.0, "confidence": confidence, "n_resamples": n_resamples}
    rng = Random(seed)
    estimates = sorted(statistic(rng.choices(sample, k=len(sample))) for _ in range(n_resamples))
    alpha = (1.0 - confidence) / 2.0
    lower_index = max(0, int(alpha * n_resamples))
    upper_index = min(n_resamples - 1, int((1.0 - alpha) * n_resamples) - 1)
    return {"estimate": float(statistic(sample)), "lower": float(estimates[lower_index]),
            "upper": float(estimates[upper_index]), "confidence": confidence, "n_resamples": n_resamples}

def paired_metric_comparison(baseline: Sequence[float], candidate: Sequence[float]) -> dict:
    if len(baseline) != len(candidate):
        raise ValueError("paired comparisons require equal-length sequences")
    deltas = [float(new) - float(old) for old, new in zip(baseline, candidate)]
    return {"n_pairs": len(deltas), "mean_delta": safe_mean(deltas), "median_delta": safe_median(deltas),
            "delta_stddev": population_stddev(deltas), "wins": sum(d > 0 for d in deltas),
            "ties": sum(d == 0 for d in deltas), "losses": sum(d < 0 for d in deltas)}

def aggregate_runs(runs: Sequence[RunTrace]) -> dict:
    if not runs:
        return {"n_runs": 0, "completion_rate": 0.0, "avg_sources": 0.0, "avg_source_success_rate": 0.0,
                "avg_citation_precision_proxy": 0.0, "avg_latency_seconds": 0.0, "median_latency_seconds": 0.0,
                "latency_stddev_seconds": 0.0, "avg_total_tokens": 0.0, "total_tokens_stddev": 0.0,
                "avg_estimated_cost_usd": 0.0, "median_estimated_cost_usd": 0.0}
    latencies = [run.latency_seconds for run in runs]
    total_tokens = [float(run.total_tokens) for run in runs]
    costs = [run.estimated_cost_usd for run in runs]
    return {"n_runs": len(runs), "completion_rate": safe_mean(1.0 if r.completed else 0.0 for r in runs),
            "avg_sources": safe_mean(float(r.source_count) for r in runs),
            "avg_source_success_rate": safe_mean(r.source_success_rate for r in runs),
            "avg_citation_precision_proxy": safe_mean(r.citation_precision_proxy for r in runs),
            "avg_latency_seconds": safe_mean(latencies), "median_latency_seconds": safe_median(latencies),
            "latency_stddev_seconds": population_stddev(latencies), "avg_total_tokens": safe_mean(total_tokens),
            "total_tokens_stddev": population_stddev(total_tokens), "avg_estimated_cost_usd": safe_mean(costs),
            "median_estimated_cost_usd": safe_median(costs)}

def deduplicate_sources(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for raw_url in urls:
        url = (raw_url or "").strip()
        if url and url not in seen:
            seen.add(url)
            unique.append(url)
    return unique
