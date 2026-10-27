"""Independent arithmetic audit of VERA's frozen primary paired contrasts.

This is an additional, offline read-only check, not a replacement for the
SHA-pinned provenance verifier or the preregistered historical analyzer.
It deliberately does not import scripts.analyze_main_study.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import json
import math
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


def _median(values):
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2


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

    for variant in VARIANTS:
        record = summary[variant]
        if not isinstance(record, dict) or not isinstance(record.get("means"), dict):
            raise ValueError(f"variant summary missing means: {variant}")
        _same_integer(record.get("n"), 10, f"{variant}.n")
        average = sum(cell[(variant, task)] for task in EXPECTED_TASKS) / 10
        _same_number(record["means"].get("strict_support_rate"), average,
                     f"{variant}.mean_strict_support_rate")

    exact_pvalues = {}
    for left, right, name in CONTRASTS:
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

    # Independently check the predeclared three-test Holm family, including
    # monotonicity, without examining secondary or exploratory hypotheses.
    running = Fraction(0)
    for rank, (name, pvalue) in enumerate(
        sorted(exact_pvalues.items(), key=lambda item: (item[1], item[0]))
    ):
        running = max(running, min(Fraction(1), (3 - rank) * pvalue))
        _same_number(results[name].get("holm_adjusted_p"), running,
                     f"{name}.holm_adjusted_p")
    return {
        "status": "independent_primary_arithmetic_consistent_not_provenance",
        "paired_tasks": 10,
        "primary_contrasts_checked": 3,
        "bootstrap_intervals_checked": False,
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
