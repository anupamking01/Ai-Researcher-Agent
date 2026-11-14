"""Offline exploratory leave-one-task-out audit of VERA's cost-quality frontier.

No main-study, evaluator, human-rating, or frozen analysis artifact is changed.
This describes every single-task omission; it is not confirmatory inference.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import statistics
from pathlib import Path

from scripts import analyze_main_study as frozen
from scripts import analyze_main_study_task_influence as custody
from scripts import verify_analysis_provenance

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path("outputs/main_study_runs.csv")
SUPPORT = Path("outputs/posthoc_support_runs.csv")
INFERENCE = custody.INFERENCE
PROVENANCE = custody.PROVENANCE


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _rows(data: bytes, *, label: str, required: set[str]) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    columns = reader.fieldnames
    _require(columns is not None and len(columns) == len(set(columns))
             and required <= set(columns), f"{label} header missing or ambiguous")
    try:
        records = list(reader)
    except csv.Error as exc:
        raise ValueError(f"{label} has malformed CSV") from exc
    _require(bool(records), f"{label} is empty")
    _require(all(None not in row and all(value is not None for value in row.values())
                 for row in records), f"{label} has extra or missing columns")
    return records


def _count(raw: str, label: str) -> int:
    _require(isinstance(raw, str) and re.fullmatch(r"(?:0|[1-9][0-9]*)", raw),
             f"{label} must be an exact non-negative integer")
    return int(raw)


def _finite(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"{label} must be finite numeric evidence") from exc
    _require(math.isfinite(value) and value >= 0, f"{label} must be finite nonnegative")
    return value


def _indexed(records: list[dict[str, str]], *, label: str,
             allowed: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    indexed = {}
    for row in records:
        key = (row.get("variant_id"), row.get("task_id"))
        _require(key in allowed, f"{label} contains unexpected task/treatment cell: {key}")
        _require(key not in indexed, f"{label} has duplicate task/treatment cell: {key}")
        indexed[key] = row
    _require(set(indexed) == allowed, f"{label} incomplete frozen treatment matrix")
    return indexed


def diagnostic(analysis: dict, main_bytes: bytes, support_bytes: bytes) -> dict:
    """Enumerate all 10 single-task cost-quality frontiers, never selecting one."""
    _require(type(analysis) is dict
             and type(analysis.get("schema_version")) is int
             and analysis["schema_version"] == 1
             and analysis.get("study_id") == "budget-main-v1"
             and analysis.get("primary_outcome") == "strict_support_rate",
             "unexpected canonical inference identity")
    tasks = analysis.get("task_ids")
    _require(type(tasks) is list and len(tasks) == frozen.EXPECTED_TASKS
             and all(type(t) is str and t and t == t.strip() for t in tasks)
             and len(set(tasks)) == len(tasks)
             and type(analysis.get("n_tasks")) is int
             and analysis["n_tasks"] == len(tasks),
             "incomplete or ambiguous frozen task identity")
    variants = tuple(frozen.VARIANTS)
    allowed = {(variant, task) for variant in variants for task in tasks}
    main = _indexed(_rows(main_bytes, label="treatments", required={
        "variant_id", "task_id", "completed", "treatment_cost_usd",
        "posthoc_claims_checked", "posthoc_strict_support_rate",
    }), label="treatments", allowed=allowed)
    support = _indexed(_rows(support_bytes, label="common evaluator", required={
        "variant_id", "task_id", "claims_checked", "supported",
        "partially_supported", "unsupported", "contradicted", "strict_support_rate",
    }), label="common evaluator", allowed=allowed)

    values = {}
    for key in sorted(allowed):
        observed = support[key]
        counts = [_count(observed[name], f"{key}/{name}") for name in (
            "claims_checked", "supported", "partially_supported",
            "unsupported", "contradicted",
        )]
        claims, supported, partial, unsupported, contradicted = counts
        _require(0 < claims <= 12 and supported + partial + unsupported + contradicted == claims,
                 f"{key} common evaluator claims/counts mismatch")
        rate = supported / claims
        _require(math.isclose(_finite(observed["strict_support_rate"], f"{key}/strict_rate"),
                              rate, rel_tol=0, abs_tol=1e-12),
                 f"{key} evaluator strict rate/count mismatch")
        treatment = main[key]
        _require(treatment["completed"] == "True", f"{key} treatment not completed")
        _require(_count(treatment["posthoc_claims_checked"], f"{key}/main_claims") == claims,
                 f"{key} treatment/evaluator claim-count mismatch")
        _require(math.isclose(_finite(treatment["posthoc_strict_support_rate"],
                                      f"{key}/main_strict_rate"), rate,
                              rel_tol=0, abs_tol=1e-12),
                 f"{key} treatment/evaluator strict-rate mismatch")
        values[key] = (rate, _finite(treatment["treatment_cost_usd"], f"{key}/cost"))

    def summarize(retained: list[str]) -> dict:
        return {variant: {"n": len(retained), "means": {
            "strict_support_rate": statistics.mean(values[(variant, task)][0] for task in retained),
            "treatment_cost_usd": statistics.mean(values[(variant, task)][1] for task in retained),
        }} for variant in variants}

    full = summarize(tasks)
    stated = analysis.get("variant_summary")
    _require(type(stated) is dict and set(stated) == set(variants),
             "canonical variant summary mismatch")
    for variant in variants:
        published = stated[variant]
        _require(type(published) is dict and type(published.get("n")) is int
                 and published["n"] == len(tasks)
                 and type(published.get("means")) is dict,
                 f"{variant} invalid canonical variant summary")
        for metric, computed in full[variant]["means"].items():
            observed = published["means"].get(metric)
            _require(type(observed) in (int, float) and math.isfinite(observed)
                     and math.isclose(observed, computed, rel_tol=0, abs_tol=1e-12),
                     f"{variant}/{metric} inconsistent with published canonical mean")
    primary = analysis.get("primary_contrasts")
    _require(type(primary) is dict and set(primary) == {
        name for _, _, name in frozen.PRIMARY_CONTRASTS
    }, "canonical primary contrast set mismatch")
    for left, right, name in frozen.PRIMARY_CONTRASTS:
        published = primary[name]
        _require(type(published) is dict and type(published.get("task_differences")) is list
                 and len(published["task_differences"]) == len(tasks),
                 f"{name} canonical task differences mismatch")
        for task, expected in zip(tasks, published["task_differences"]):
            computed = values[(right, task)][0] - values[(left, task)][0]
            _require(type(expected) in (int, float) and math.isfinite(expected)
                     and math.isclose(expected, computed, rel_tol=0, abs_tol=1e-12),
                     f"{name}/{task} not bound to canonical paired differences")

    baseline = frozen._pareto_frontier(full)
    _require(analysis.get("cost_quality_pareto") == baseline,
             "full-sample cost-quality frontier not canonical")
    omissions = []
    membership = {variant: 0 for variant in variants}
    for omitted in tasks:
        kept = [task for task in tasks if task != omitted]
        means = summarize(kept)
        frontier = frozen._pareto_frontier(means)
        for variant in frontier["frontier"]:
            membership[variant] += 1
        omissions.append({
            "omitted_task_id": omitted,
            "retained_task_count": len(kept),
            "frontier": frontier["frontier"],
            "dominated_by": frontier["dominated_by"],
            "variant_means": {v: means[v]["means"] for v in variants},
            "frontier_differs_from_full_sample": frontier["frontier"] != baseline["frontier"],
        })
    return {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "post_hoc_exploratory_pareto_stability_only",
        "confirmatory_analysis_replaced": False,
        "human_validation_performed": False,
        "inferential_p_values_or_intervals_added": False,
        "task_ids": list(tasks),
        "full_sample_frontier": baseline["frontier"],
        "full_sample_variant_means": {v: full[v]["means"] for v in variants},
        "all_task_omissions": omissions,
        "frontier_membership_counts_of_ten_omissions": membership,
        "omissions_with_changed_frontier": sum(row["frontier_differs_from_full_sample"]
                                               for row in omissions),
    }


def run_verified(root: Path = ROOT) -> dict:
    """Check the existing execution/recompute chain and retained CSV identities."""
    root = Path(root)
    sources = {name: root / relative for name, relative in (
        ("main_study_runs", MAIN), ("posthoc_support_runs", SUPPORT),
    )}
    before = {name: custody._read_regular_bounded(path, label=name)
              for name, path in sources.items()}
    inherited = custody.run_verified(root)
    after = {name: custody._read_regular_bounded(path, label=name)
             for name, path in sources.items()}
    _require(before == after, "verified treatment/evaluator inputs changed during Pareto audit")
    receipt_bytes = custody._read_regular_bounded(root / PROVENANCE, label="provenance")
    _require(hashlib.sha256(receipt_bytes).hexdigest() ==
             inherited["verified_provenance_receipt_sha256"],
             "verified provenance receipt changed during Pareto audit")
    receipt = verify_analysis_provenance.parse_receipt_json(receipt_bytes.decode("utf-8"))
    inputs = receipt.get("verified_inputs")
    _require(type(inputs) is list and len(inputs) == 2
             and all(type(item) is dict for item in inputs),
             "verified input bindings missing")
    expected = {str(MAIN): hashlib.sha256(before["main_study_runs"]).hexdigest(),
                str(SUPPORT): hashlib.sha256(before["posthoc_support_runs"]).hexdigest()}
    _require({item.get("path"): item.get("sha256") for item in inputs} == expected,
             "treatment/evaluator input hashes not bound to verified provenance")
    inference_bytes = custody._read_regular_bounded(root / INFERENCE, label="inference")
    _require(hashlib.sha256(inference_bytes).hexdigest() ==
             inherited["verified_canonical_inference_sha256"],
             "verified canonical inference changed during Pareto audit")
    output = diagnostic(custody._parse_analysis(inference_bytes),
                        before["main_study_runs"], before["posthoc_support_runs"])
    output["verified_canonical_inference_sha256"] = inherited[
        "verified_canonical_inference_sha256"]
    output["verified_provenance_receipt_sha256"] = inherited[
        "verified_provenance_receipt_sha256"]
    output["verified_input_sha256"] = expected
    output["source_provenance_independently_recomputed"] = True
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = run_verified(args.root)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise SystemExit(f"PARETO INFLUENCE AUDIT: FAIL: {exc}") from exc
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
