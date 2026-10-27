"""Independent arithmetic audit of VERA's frozen primary paired contrasts.

This is an additional, offline read-only check, not a replacement for the
SHA-pinned provenance verifier or the preregistered historical analyzer.
It deliberately does not import scripts.analyze_main_study.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
from functools import lru_cache
from fractions import Fraction
import json
import math
import random
import statistics
from pathlib import Path

from scripts.validate_main_study_inputs import read_csv_rows, validate_rows

ROOT = Path(__file__).resolve().parents[1]
VARIANTS = ("D3", "D6", "P6", "P6V")
CONTRASTS = (
    ("D3", "D6", "D6_minus_D3_retrieval_depth"),
    ("D6", "P6", "P6_minus_D6_planning"),
    ("P6", "P6V", "P6V_minus_P6_verification"),
)
EXPECTED_TASKS = tuple(f"main-{number:02d}" for number in range(1, 11))
# These remain descriptive/exploratory, never part of the Holm primary family.
SECONDARY_METRICS = (
    "broad_support_rate", "unsupported_or_contradicted_rate",
    "successful_sources", "total_tokens", "treatment_cost_usd",
    "latency_seconds", "model_calls", "report_words",
)
TREATMENT_SECONDARY_FIELDS = (
    "successful_sources", "total_tokens", "treatment_cost_usd",
    "latency_seconds", "model_calls", "report_words",
)
ABS_TOL = 1e-12


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate inference JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-finite inference JSON token: {value}")


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite JSON number")
    actual = float(value)
    if not math.isfinite(actual):
        raise ValueError(f"{label} must be a finite JSON number")
    return actual


def _same_number(observed, expected, label):
    if not math.isclose(_finite(observed, label), float(expected),
                        rel_tol=0.0, abs_tol=ABS_TOL):
        raise ValueError(f"independent primary inference mismatch: {label}")


def _same_integer(observed, expected, label):
    if type(observed) is not int or observed != expected:
        raise ValueError(f"independent primary inference mismatch: {label}")


def _exact_signflip(differences):
    """Enumerate all 2^10 paired sign assignments with rational arithmetic."""
    target = abs(sum(differences))
    extreme = 0
    for mask in range(1 << len(differences)):
        permuted = sum(
            difference if mask & (1 << index) else -difference
            for index, difference in enumerate(differences)
        )
        if abs(permuted) >= target:
            extreme += 1
    return Fraction(extreme, 1 << len(differences))


def _bootstrap_percentile_interval(differences, *, seed, draws):
    """Independently audit the frozen task-paired percentile bootstrap.

    Reconstruct the seeded WITH-replacement task indices; use exact rational
    counts for draw means and percentile interpolation. Only the Python
    stdlib MT19937/randrange stream is shared with the frozen implementation.
    """
    if not differences or draws < 2:
        raise ValueError("bootstrap audit needs paired data and at least two draws")
    rng = random.Random(seed)
    size = len(differences)
    averages = sorted(
        sum((differences[rng.randrange(size)] for _ in range(size)), Fraction(0)) / size
        for _ in range(draws)
    )

    def percentile(numerator):
        # 1/40 and 39/40 are the prespecified 2.5% and 97.5% quantiles.
        position = Fraction((draws - 1) * numerator, 40)
        lower = position.numerator // position.denominator
        upper = min(lower + 1, draws - 1)
        return averages[lower] + (averages[upper] - averages[lower]) * (position - lower)

    return (percentile(1), percentile(39))



@lru_cache(maxsize=64)
def _secondary_bootstrap_ci(differences, *, seed, draws):
    """Reconstruct a frozen secondary paired-bootstrap interval with integers.

    The differences argument is a tuple of exact rational task-paired effects.
    Scaling by their least common denominator makes every with-replacement
    bootstrap mean and linearly interpolated percentile exact, independently
    of the historical analyzer's float/statistics helpers. Cached fixed inputs
    avoid regenerating resamples in repeated adversarial validation tests.
    """
    if not differences or draws < 2:
        raise ValueError("secondary bootstrap requires paired data and two draws")
    size = len(differences)
    denominator = math.lcm(*(value.denominator for value in differences))
    scaled = tuple(
        value.numerator * (denominator // value.denominator)
        for value in differences
    )
    rng = random.Random(seed)
    sampled_sums = sorted(
        sum(scaled[rng.randrange(size)] for _ in range(size))
        for _ in range(draws)
    )

    def percentile(numerator):
        position = Fraction((draws - 1) * numerator, 40)
        lower = position.numerator // position.denominator
        upper = min(lower + 1, draws - 1)
        interpolated_sum = (
            Fraction(sampled_sums[lower])
            + (sampled_sums[upper] - sampled_sums[lower]) * (position - lower)
        )
        return interpolated_sum / (size * denominator)

    return (percentile(1), percentile(39))

def _median(values):
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


def _secondary_values(treatment, evaluator):
    """Derive secondary outcomes independently from captured CSV text.

    Decimal-to-Fraction conversion avoids using the historical analyzer's
    float parser or paired-summary helpers. The existing scientific preflight
    has already validated these columns and their numeric domains.
    """
    checked = int(evaluator["claims_checked"])
    measures = {
        "broad_support_rate": Fraction(
            int(evaluator["supported"]) + int(evaluator["partially_supported"]), checked
        ),
        "unsupported_or_contradicted_rate": Fraction(
            int(evaluator["unsupported"]) + int(evaluator["contradicted"]), checked
        ),
    }
    for field in TREATMENT_SECONDARY_FIELDS:
        measures[field] = Fraction(Decimal(treatment[field]))
    return measures


def _audit_secondary_pair(recorded, left_values, right_values, label, *, seed, draws):
    """Check exploratory paired descriptors, including frozen bootstrap intervals."""
    if not isinstance(recorded, dict):
        raise ValueError(f"secondary paired descriptive must be an object: {label}")
    differences = [right - left for left, right in zip(left_values, right_values)]
    if len(differences) != len(EXPECTED_TASKS):
        raise ValueError(f"secondary paired matrix mismatch: {label}")
    mean = sum(differences, Fraction(0)) / len(differences)
    _same_integer(recorded.get("n_pairs"), len(differences), f"{label}.n_pairs")
    for field, expected in (
        ("left_mean", sum(left_values, Fraction(0)) / len(left_values)),
        ("right_mean", sum(right_values, Fraction(0)) / len(right_values)),
        ("mean_difference", mean),
        ("median_difference", _median(differences)),
    ):
        _same_number(recorded.get(field), expected, f"{label}.{field}")
    shown = recorded.get("task_differences")
    if not isinstance(shown, list) or len(shown) != len(EXPECTED_TASKS):
        raise ValueError(f"secondary paired task_differences mismatch: {label}")
    for task, observed, expected in zip(EXPECTED_TASKS, shown, differences):
        _same_number(observed, expected, f"{label}.task_differences[{task}]")
    for field, expected in (
        ("positive_tasks", sum(d > 0 for d in differences)),
        ("negative_tasks", sum(d < 0 for d in differences)),
        ("tied_tasks", sum(d == 0 for d in differences)),
    ):
        _same_integer(recorded.get(field), expected, f"{label}.{field}")
    variance = sum((difference - mean) ** 2 for difference in differences) / (
        len(differences) - 1
    )
    if variance == 0:
        if recorded.get("paired_dz") is not None:
            raise ValueError(f"secondary paired_dz mismatch: {label}")
    else:
        _same_number(
            recorded.get("paired_dz"), float(mean) / math.sqrt(float(variance)),
            f"{label}.paired_dz",
        )
    interval = recorded.get("bootstrap_95pct_ci_mean_difference")
    if not isinstance(interval, list) or len(interval) != 2:
        raise ValueError(f"secondary bootstrap interval schema mismatch: {label}")
    expected_interval = _secondary_bootstrap_ci(
        tuple(differences), seed=seed, draws=draws
    )
    for endpoint, (observed, expected) in enumerate(zip(interval, expected_interval)):
        _same_number(
            observed, expected,
            f"{label}.bootstrap_95pct_ci_mean_difference[{endpoint}]",
        )


PARETO_NOTE = (
    "Maximize mean strict support while minimizing mean treatment cost; "
    "evaluator cost excluded."
)


def _audit_cost_quality_pareto(recorded, strict_means, treatment_cost_means):
    """Independently derive the archived descriptive two-objective frontier.

    Exact rational comparisons avoid rounded table means introducing or
    erasing a dominance relation. This is descriptive, not a new hypothesis
    test or a recommendation to select treatments post hoc.
    """
    if not isinstance(recorded, dict) or set(recorded) != {
        "frontier", "dominated_by", "note",
    }:
        raise ValueError("independent cost-quality Pareto mismatch: schema")
    if set(strict_means) != set(VARIANTS) or set(treatment_cost_means) != set(VARIANTS):
        raise ValueError("independent cost-quality Pareto mismatch: variant means")

    expected_dominated = {}
    for candidate in VARIANTS:
        expected_dominated[candidate] = [
            other for other in VARIANTS
            if other != candidate
            and strict_means[other] >= strict_means[candidate]
            and treatment_cost_means[other] <= treatment_cost_means[candidate]
            and (
                strict_means[other] > strict_means[candidate]
                or treatment_cost_means[other] < treatment_cost_means[candidate]
            )
        ]
    expected_frontier = [
        candidate for candidate in VARIANTS
        if not expected_dominated[candidate]
    ]

    dominated_by = recorded["dominated_by"]
    if not isinstance(dominated_by, dict) or set(dominated_by) != set(VARIANTS):
        raise ValueError("independent cost-quality Pareto mismatch: dominated_by schema")
    for candidate in VARIANTS:
        actual = dominated_by[candidate]
        if type(actual) is not list or actual != expected_dominated[candidate]:
            raise ValueError(
                f"independent cost-quality Pareto mismatch: dominated_by[{candidate}]"
            )
    if type(recorded["frontier"]) is not list or recorded["frontier"] != expected_frontier:
        raise ValueError("independent cost-quality Pareto mismatch: frontier")
    if recorded["note"] != PARETO_NOTE:
        raise ValueError("independent cost-quality Pareto mismatch: cost scope note")


def audit_primary(treatment_rows, evaluator_rows, inference):
    """Cross-check primary estimates using raw counts, not analyzer functions."""
    # The historical, SHA-pinned CSV export precedes the newer mandatory
    # pricing-file metadata required by the strict prospective export contract.
    # Apply row-level validity and separately require the exact frozen matrix
    # and cross-file support mirrors; do not pretend this legacy export meets
    # the prospective provenance schema.
    validate_rows(treatment_rows, evaluator_rows, require_canonical_matrix=False)
    expected_cells = {(variant, task) for variant in VARIANTS for task in EXPECTED_TASKS}
    main_cells = {(row["variant_id"], row["task_id"]) for row in treatment_rows}
    support_cells = {(row["variant_id"], row["task_id"]) for row in evaluator_rows}
    if main_cells != expected_cells or support_cells != expected_cells:
        raise ValueError("frozen matrix mismatch in primary inference inputs")
    main_by_cell = {(row["variant_id"], row["task_id"]): row for row in treatment_rows}
    for row in evaluator_rows:
        key = (row["variant_id"], row["task_id"])
        mirror = main_by_cell[key]
        if int(mirror["posthoc_claims_checked"]) != int(row["claims_checked"]):
            raise ValueError(f"evaluator mirror mismatch: {key}/claims_checked")
        checked_rate = Fraction(int(row["supported"]), int(row["claims_checked"]))
        if not math.isclose(
            _finite(float(mirror["posthoc_strict_support_rate"]), "posthoc_strict_support_rate"),
            float(checked_rate), rel_tol=0.0, abs_tol=ABS_TOL
        ):
            raise ValueError(f"evaluator mirror mismatch: {key}/strict_support_rate")
    if not isinstance(inference, dict):
        raise ValueError("inference must be a JSON object")
    if (
        type(inference.get("schema_version")) is not int
        or inference["schema_version"] != 1
        or inference.get("study_id") != "budget-main-v1"
        or inference.get("primary_outcome") != "strict_support_rate"
        or inference.get("analysis_plan") != "paper/ANALYSIS_PLAN.md"
    ):
        raise ValueError("unexpected inference study/analysis schema")
    _same_integer(inference.get("n_tasks"), 10, "n_tasks")
    _same_integer(inference.get("bootstrap_seed"), 20260914, "bootstrap_seed")
    _same_integer(inference.get("bootstrap_draws"), 20000, "bootstrap_draws")
    if inference.get("task_ids") != list(EXPECTED_TASKS):
        raise ValueError("independent primary inference mismatch: task_ids")

    summary = inference.get("variant_summary")
    results = inference.get("primary_contrasts")
    if not isinstance(summary, dict) or set(summary) != set(VARIANTS):
        raise ValueError("variant summary schema mismatch")
    if not isinstance(results, dict) or set(results) != {c[2] for c in CONTRASTS}:
        raise ValueError("primary contrast schema mismatch")

    # Work with exact rational report-level support rates to make comparison
    # independent of the historical analyzer's floating-point implementation.
    cell = {}
    for row in evaluator_rows:
        identity = (row["variant_id"], row["task_id"])
        cell[identity] = Fraction(int(row["supported"]), int(row["claims_checked"]))

    secondary_cells = {
        key: _secondary_values(main_by_cell[key], row)
        for row in evaluator_rows
        for key in [(row["variant_id"], row["task_id"])]
    }

    for variant in VARIANTS:
        record = summary[variant]
        if not isinstance(record, dict) or not isinstance(record.get("means"), dict):
            raise ValueError(f"variant summary missing means: {variant}")
        _same_integer(record.get("n"), 10, f"{variant}.n")
        average = sum(cell[(variant, task)] for task in EXPECTED_TASKS) / 10
        _same_number(record["means"].get("strict_support_rate"), average,
                     f"{variant}.mean_strict_support_rate")
        _same_integer(
            record.get("zero_evidence_runs"),
            sum(
                row["variant_id"] == variant
                and row["evidence_status"] == "zero_successful_sources"
                for row in evaluator_rows
            ),
            f"{variant}.zero_evidence_runs",
        )
        if set(record["means"]) != {"strict_support_rate", *SECONDARY_METRICS}:
            raise ValueError(f"secondary mean metric schema mismatch: {variant}")
        for metric in SECONDARY_METRICS:
            expected_mean = sum(
                (secondary_cells[(variant, task)][metric] for task in EXPECTED_TASKS),
                Fraction(0),
            ) / len(EXPECTED_TASKS)
            _same_number(
                record["means"].get(metric), expected_mean,
                f"{variant}.mean_{metric}",
            )

    exact_pvalues = {}
    for contrast_index, (left, right, name) in enumerate(CONTRASTS):
        recorded = results[name]
        if not isinstance(recorded, dict):
            raise ValueError(f"primary contrast must be an object: {name}")
        differences = [
            cell[(right, task)] - cell[(left, task)] for task in EXPECTED_TASKS
        ]
        left_mean = sum(cell[(left, task)] for task in EXPECTED_TASKS) / 10
        right_mean = sum(cell[(right, task)] for task in EXPECTED_TASKS) / 10
        mean = sum(differences) / 10
        _same_integer(recorded.get("n_pairs"), 10, f"{name}.n_pairs")
        for key, expected in (
            ("left_mean", left_mean),
            ("right_mean", right_mean),
            ("mean_difference", mean),
            ("median_difference", _median(differences)),
        ):
            _same_number(recorded.get(key), expected, f"{name}.{key}")

        shown = recorded.get("task_differences")
        if not isinstance(shown, list) or len(shown) != 10:
            raise ValueError(f"independent primary inference mismatch: {name}.task_differences")
        for task, observed, expected in zip(EXPECTED_TASKS, shown, differences):
            _same_number(observed, expected, f"{name}.task_differences[{task}]")
        for key, expected in (
            ("positive_tasks", sum(d > 0 for d in differences)),
            ("negative_tasks", sum(d < 0 for d in differences)),
            ("tied_tasks", sum(d == 0 for d in differences)),
        ):
            _same_integer(recorded.get(key), expected, f"{name}.{key}")

        variance = sum((d - mean) ** 2 for d in differences) / 9
        dz = recorded.get("paired_dz")
        if variance == 0:
            if dz is not None:
                raise ValueError(f"independent primary inference mismatch: {name}.paired_dz")
        else:
            _same_number(dz, float(mean) / math.sqrt(float(variance)),
                         f"{name}.paired_dz")
        pvalue = _exact_signflip(differences)
        _same_number(recorded.get("exact_two_sided_signflip_p"), pvalue,
                     f"{name}.exact_two_sided_signflip_p")
        exact_pvalues[name] = pvalue

        recorded_interval = recorded.get("bootstrap_95pct_ci_mean_difference")
        if not isinstance(recorded_interval, list) or len(recorded_interval) != 2:
            raise ValueError(
                f"independent primary inference mismatch: {name}.bootstrap_95pct_ci_mean_difference"
            )
        expected_interval = _bootstrap_percentile_interval(
            differences, seed=20260914 + contrast_index, draws=20_000
        )
        for endpoint, (observed, expected) in enumerate(
            zip(recorded_interval, expected_interval)
        ):
            _same_number(
                observed, expected,
                f"{name}.bootstrap_95pct_ci_mean_difference[{endpoint}]"
            )

    # Independently check the predeclared three-test Holm family, including
    # monotonicity, without examining secondary or exploratory hypotheses.
    running = Fraction(0)
    for rank, (name, pvalue) in enumerate(
        sorted(exact_pvalues.items(), key=lambda item: (item[1], item[0]))
    ):
        running = max(running, min(Fraction(1), (3 - rank) * pvalue))
        _same_number(results[name].get("holm_adjusted_p"), running,
                     f"{name}.holm_adjusted_p")

    # These are *exploratory descriptors*. Deliberately do not add their
    # statistics to the frozen confirmatory family or inspect/rerun treatments.
    secondary = inference.get("secondary_paired_descriptives")
    if not isinstance(secondary, dict) or set(secondary) != {c[2] for c in CONTRASTS}:
        raise ValueError("secondary paired contrast schema mismatch")
    for contrast_index, (left, right, name) in enumerate(CONTRASTS):
        metrics = secondary[name]
        if not isinstance(metrics, dict) or set(metrics) != set(SECONDARY_METRICS):
            raise ValueError(f"secondary paired metric schema mismatch: {name}")
        for metric_index, metric in enumerate(SECONDARY_METRICS):
            _audit_secondary_pair(
                metrics[metric],
                [secondary_cells[(left, task)][metric] for task in EXPECTED_TASKS],
                [secondary_cells[(right, task)][metric] for task in EXPECTED_TASKS],
                f"{name}.{metric}",
                seed=20260914 + 100 + 10 * contrast_index + metric_index,
                draws=20_000,
            )

    # Check the originally reported descriptive cost-quality frontier against
    # exact means from the retained report-level records, not from the
    # inference JSON being audited. This does not add confirmatory tests.
    pareto_support_means = {
        variant: sum(
            (cell[(variant, task)] for task in EXPECTED_TASKS), Fraction(0)
        ) / len(EXPECTED_TASKS)
        for variant in VARIANTS
    }
    pareto_cost_means = {
        variant: sum(
            (secondary_cells[(variant, task)]["treatment_cost_usd"]
             for task in EXPECTED_TASKS), Fraction(0)
        ) / len(EXPECTED_TASKS)
        for variant in VARIANTS
    }
    _audit_cost_quality_pareto(
        inference.get("cost_quality_pareto"),
        pareto_support_means,
        pareto_cost_means,
    )
    return {
        "status": "independent_primary_arithmetic_consistent_not_provenance",
        "paired_tasks": 10,
        "primary_contrasts_checked": 3,
        "bootstrap_intervals_checked": True,
        "secondary_variant_means_checked": len(VARIANTS) * len(SECONDARY_METRICS),
        "secondary_paired_descriptives_checked": len(CONTRASTS) * len(SECONDARY_METRICS),
        "secondary_bootstrap_intervals_checked": len(CONTRASTS) * len(SECONDARY_METRICS),
        "cost_quality_pareto_checked": True,
    }


def audit_files(main_csv: Path, support_csv: Path, inference_json: Path):
    if inference_json.is_symlink() or not inference_json.is_file():
        raise ValueError("inference JSON must be a regular file")
    if inference_json.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("inference JSON exceeds size limit")
    inference = json.loads(
        inference_json.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_keys,
        parse_constant=_reject_constant,
    )
    return audit_primary(read_csv_rows(main_csv), read_csv_rows(support_csv), inference)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main", type=Path, default=ROOT / "outputs/main_study_runs.csv")
    parser.add_argument("--evaluator", type=Path, default=ROOT / "outputs/posthoc_support_runs.csv")
    parser.add_argument("--inference", type=Path, default=ROOT / "outputs/main_study_inference.json")
    args = parser.parse_args()
    print(json.dumps(audit_files(args.main, args.evaluator, args.inference), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
