"""Preregistered paired inference for the budget main study.

This script implements paper/ANALYSIS_PLAN.md. It is offline: it makes no
network/model calls and reads only the completed treatment/evaluator CSVs.
"""

from __future__ import annotations

import csv
import itertools
import json
import math
import random
import statistics
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_CSV = REPO_ROOT / "outputs" / "main_study_runs.csv"
SUPPORT_CSV = REPO_ROOT / "outputs" / "posthoc_support_runs.csv"
OUT_JSON = REPO_ROOT / "outputs" / "main_study_inference.json"
OUT_MD = REPO_ROOT / "paper" / "MAIN_STUDY_INFERENCE.md"

VARIANTS = ("D3", "D6", "P6", "P6V")
PRIMARY_CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
BOOTSTRAP_SEED = 20260914
BOOTSTRAP_DRAWS = 20_000
EXPECTED_TASKS = 10


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SystemExit(f"Missing required input: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _float(row: dict[str, str], key: str) -> float:
    value = row.get(key)
    if value in (None, ""):
        raise SystemExit(f"Missing numeric field {key!r} in row {row}")
    return float(value)


def _int(row: dict[str, str], key: str) -> int:
    return int(round(_float(row, key)))


def _mean(values: list[float]) -> float:
    return statistics.mean(values)


def _percentile(sorted_values: list[float], q: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    weight = pos - lo
    return sorted_values[lo] * (1.0 - weight) + sorted_values[hi] * weight


def _bootstrap_mean_ci(diffs: list[float], seed: int) -> list[float]:
    rng = random.Random(seed)
    n = len(diffs)
    draws = []
    for _ in range(BOOTSTRAP_DRAWS):
        draws.append(_mean([diffs[rng.randrange(n)] for _ in range(n)]))
    draws.sort()
    return [_percentile(draws, 0.025), _percentile(draws, 0.975)]


def _exact_signflip_pvalue(diffs: list[float]) -> float:
    """Exact two-sided randomization p-value for a paired mean difference."""
    observed = abs(_mean(diffs))
    eps = 1e-15
    extreme = 0
    total = 0
    for signs in itertools.product((-1.0, 1.0), repeat=len(diffs)):
        permuted = abs(_mean([d * s for d, s in zip(diffs, signs)]))
        total += 1
        if permuted + eps >= observed:
            extreme += 1
    return extreme / total


def _paired_summary(
    left: list[float], right: list[float], *, seed: int, exact_p: bool
) -> dict:
    if len(left) != len(right) or not left:
        raise ValueError("paired vectors must be non-empty and equal length")
    diffs = [b - a for a, b in zip(left, right)]
    sd = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    result = {
        "n_pairs": len(diffs),
        "left_mean": _mean(left),
        "right_mean": _mean(right),
        "mean_difference": _mean(diffs),
        "median_difference": statistics.median(diffs),
        "bootstrap_95pct_ci_mean_difference": _bootstrap_mean_ci(diffs, seed),
        "paired_dz": (_mean(diffs) / sd) if sd > 0 else None,
        "positive_tasks": sum(d > 0 for d in diffs),
        "negative_tasks": sum(d < 0 for d in diffs),
        "tied_tasks": sum(d == 0 for d in diffs),
        "task_differences": diffs,
    }
    if exact_p:
        result["exact_two_sided_signflip_p"] = _exact_signflip_pvalue(diffs)
    return result


def _holm_adjust(items: list[tuple[str, float]]) -> dict[str, float]:
    """Holm step-down adjusted p-values, monotone and capped at 1."""
    ordered = sorted(items, key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, pvalue) in enumerate(ordered):
        candidate = min(1.0, (m - rank) * pvalue)
        running = max(running, candidate)
        adjusted[name] = min(1.0, running)
    return adjusted


def _build_dataset() -> tuple[dict[tuple[str, str], dict], list[str]]:
    main_rows = _read_csv(MAIN_CSV)
    support_rows = _read_csv(SUPPORT_CSV)

    main: dict[tuple[str, str], dict[str, str]] = {}
    for row in main_rows:
        key = (row.get("variant_id", ""), row.get("task_id", ""))
        if key in main:
            raise SystemExit(f"Duplicate treatment row: {key}")
        main[key] = row

    support: dict[tuple[str, str], dict[str, str]] = {}
    for row in support_rows:
        key = (row.get("variant_id", ""), row.get("task_id", ""))
        if key in support:
            raise SystemExit(f"Duplicate evaluator row: {key}")
        support[key] = row

    task_sets = []
    for variant in VARIANTS:
        tasks = {task for (v, task) in main if v == variant}
        support_tasks = {task for (v, task) in support if v == variant}
        if len(tasks) != EXPECTED_TASKS:
            raise SystemExit(f"{variant} has {len(tasks)} treatment tasks; expected {EXPECTED_TASKS}")
        if tasks != support_tasks:
            raise SystemExit(
                f"Treatment/evaluator task mismatch for {variant}: "
                f"treatment={sorted(tasks)} evaluator={sorted(support_tasks)}"
            )
        task_sets.append(tasks)

    if any(tasks != task_sets[0] for tasks in task_sets[1:]):
        raise SystemExit("Variants do not share the same frozen task set")
    tasks = sorted(task_sets[0])
    if len(main) != EXPECTED_TASKS * len(VARIANTS):
        raise SystemExit(f"Treatment matrix has {len(main)} rows; expected 40")
    if len(support) != EXPECTED_TASKS * len(VARIANTS):
        raise SystemExit(f"Evaluator matrix has {len(support)} rows; expected 40")

    joined: dict[tuple[str, str], dict] = {}
    for variant in VARIANTS:
        for task in tasks:
            m = main[(variant, task)]
            e = support[(variant, task)]
            completed = str(m.get("completed", "")).strip().lower()
            if completed not in {"true", "1", "yes"}:
                raise SystemExit(f"Incomplete treatment cell: {variant}/{task}")
            claims = _int(e, "claims_checked")
            if claims <= 0:
                raise SystemExit(f"Evaluator checked zero claims: {variant}/{task}")
            supported = _int(e, "supported")
            partial = _int(e, "partially_supported")
            unsupported = _int(e, "unsupported")
            contradicted = _int(e, "contradicted")
            if supported + partial + unsupported + contradicted != claims:
                raise SystemExit(f"Evaluator count mismatch: {variant}/{task}")

            joined[(variant, task)] = {
                "strict_support_rate": supported / claims,
                "broad_support_rate": (supported + partial) / claims,
                "unsupported_or_contradicted_rate": (unsupported + contradicted) / claims,
                "successful_sources": _float(m, "successful_sources"),
                "total_tokens": _float(m, "total_tokens"),
                "treatment_cost_usd": _float(m, "treatment_cost_usd"),
                "latency_seconds": _float(m, "latency_seconds"),
                "model_calls": _float(m, "model_calls"),
                "report_words": _float(m, "report_words"),
                "claims_checked": claims,
                "evidence_status": e.get("evidence_status", ""),
            }
    return joined, tasks


def _variant_summary(dataset: dict[tuple[str, str], dict], tasks: list[str]) -> dict:
    metrics = (
        "strict_support_rate",
        "broad_support_rate",
        "unsupported_or_contradicted_rate",
        "successful_sources",
        "total_tokens",
        "treatment_cost_usd",
        "latency_seconds",
        "model_calls",
        "report_words",
    )
    result = {}
    for variant in VARIANTS:
        result[variant] = {
            "n": len(tasks),
            "zero_evidence_runs": sum(
                dataset[(variant, task)]["evidence_status"] == "zero_successful_sources"
                for task in tasks
            ),
            "means": {
                metric: _mean([dataset[(variant, task)][metric] for task in tasks])
                for metric in metrics
            },
        }
    return result


def _pareto_frontier(variant_summary: dict) -> dict:
    dominated_by: dict[str, list[str]] = {variant: [] for variant in VARIANTS}
    for candidate in VARIANTS:
        c = variant_summary[candidate]["means"]
        for other in VARIANTS:
            if other == candidate:
                continue
            o = variant_summary[other]["means"]
            no_worse = (
                o["strict_support_rate"] >= c["strict_support_rate"]
                and o["treatment_cost_usd"] <= c["treatment_cost_usd"]
            )
            strictly_better = (
                o["strict_support_rate"] > c["strict_support_rate"]
                or o["treatment_cost_usd"] < c["treatment_cost_usd"]
            )
            if no_worse and strictly_better:
                dominated_by[candidate].append(other)
    return {
        "frontier": [v for v in VARIANTS if not dominated_by[v]],
        "dominated_by": dominated_by,
        "note": "Maximize mean strict support while minimizing mean treatment cost; evaluator cost excluded.",
    }


def _fmt(value: float | None, digits: int = 4) -> str:
    return "NA" if value is None else f"{value:.{digits}f}"


def _markdown(payload: dict) -> str:
    lines = [
        "# Main-study inferential results",
        "",
        "Generated offline by `scripts/analyze_main_study.py` under the frozen rules in `paper/ANALYSIS_PLAN.md`.",
        "",
        "## Variant means",
        "",
        "| Variant | Strict support | Broad support | Sources | Tokens | Treatment cost | Latency (s) | Zero-evidence runs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for variant in VARIANTS:
        row = payload["variant_summary"][variant]
        m = row["means"]
        lines.append(
            f"| {variant} | {_fmt(m['strict_support_rate'])} | {_fmt(m['broad_support_rate'])} | "
            f"{_fmt(m['successful_sources'], 2)} | {_fmt(m['total_tokens'], 1)} | "
            f"${_fmt(m['treatment_cost_usd'])} | {_fmt(m['latency_seconds'], 1)} | {row['zero_evidence_runs']} |"
        )

    lines += ["", "## Primary paired contrasts: strict support", ""]
    for name, result in payload["primary_contrasts"].items():
        lines += [
            f"### {name}",
            "",
            f"- Mean paired difference: **{_fmt(result['mean_difference'])}**",
            f"- Median paired difference: {_fmt(result['median_difference'])}",
            f"- Paired-bootstrap 95% CI: [{_fmt(result['bootstrap_95pct_ci_mean_difference'][0])}, {_fmt(result['bootstrap_95pct_ci_mean_difference'][1])}]",
            f"- Exact two-sided sign-flip p: {_fmt(result['exact_two_sided_signflip_p'])}",
            f"- Holm-adjusted p across the three primary contrasts: {_fmt(result['holm_adjusted_p'])}",
            f"- Paired d_z: {_fmt(result['paired_dz'])}",
            f"- Task direction: {result['positive_tasks']} positive / {result['negative_tasks']} negative / {result['tied_tasks']} tied",
            "",
        ]

    lines += ["## Cost-quality Pareto view", ""]
    lines.append("Non-dominated variants: " + ", ".join(payload["cost_quality_pareto"]["frontier"]))
    lines += [
        "",
        "## Interpretation constraints",
        "",
        "- The 10-task set is an original live-web set, not an established public benchmark.",
        "- The common support evaluator is automated; blinded human quality scoring remains necessary.",
        "- Primary inference is limited to the three preregistered strict-support contrasts.",
        "- Live-web availability can vary across treatment executions.",
        "- Later duplicate executions must not replace the primary dataset based on favorable outcomes.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    dataset, tasks = _build_dataset()
    variant_summary = _variant_summary(dataset, tasks)

    primary = {}
    pvalues = []
    for index, (left, right, name) in enumerate(PRIMARY_CONTRASTS):
        left_values = [dataset[(left, task)]["strict_support_rate"] for task in tasks]
        right_values = [dataset[(right, task)]["strict_support_rate"] for task in tasks]
        result = _paired_summary(
            left_values,
            right_values,
            seed=BOOTSTRAP_SEED + index,
            exact_p=True,
        )
        primary[name] = result
        pvalues.append((name, result["exact_two_sided_signflip_p"]))

    adjusted = _holm_adjust(pvalues)
    for name, value in adjusted.items():
        primary[name]["holm_adjusted_p"] = value

    secondary_metrics = (
        "broad_support_rate",
        "unsupported_or_contradicted_rate",
        "successful_sources",
        "total_tokens",
        "treatment_cost_usd",
        "latency_seconds",
        "model_calls",
        "report_words",
    )
    secondary = {}
    for contrast_index, (left, right, name) in enumerate(PRIMARY_CONTRASTS):
        secondary[name] = {}
        for metric_index, metric in enumerate(secondary_metrics):
            left_values = [dataset[(left, task)][metric] for task in tasks]
            right_values = [dataset[(right, task)][metric] for task in tasks]
            secondary[name][metric] = _paired_summary(
                left_values,
                right_values,
                seed=BOOTSTRAP_SEED + 100 + 10 * contrast_index + metric_index,
                exact_p=False,
            )

    payload = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "analysis_plan": "paper/ANALYSIS_PLAN.md",
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "task_ids": tasks,
        "n_tasks": len(tasks),
        "variant_summary": variant_summary,
        "primary_outcome": "strict_support_rate",
        "primary_contrasts": primary,
        "secondary_paired_descriptives": secondary,
        "cost_quality_pareto": _pareto_frontier(variant_summary),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
