"""Independently recompute the complete exploratory Pareto artifact from retained rows.

Offline and read-only. This verifier does not import the Pareto producer, rerun
any treatment/evaluator, or change the frozen confirmatory analysis.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import statistics
from pathlib import Path

from scripts import verify_main_study_task_influence_artifact as common

VARIANTS = ("D3", "D6", "P6", "P6V")
MAIN = Path("outputs/main_study_runs.csv")
SUPPORT = Path("outputs/posthoc_support_runs.csv")
INFERENCE = Path("outputs/main_study_inference.json")
PROVENANCE = Path("outputs/main_study_analysis_provenance.json")
FIELDS = {
    "schema_version", "study_id", "status", "confirmatory_analysis_replaced",
    "human_validation_performed", "inferential_p_values_or_intervals_added",
    "task_ids", "full_sample_frontier", "full_sample_variant_means",
    "all_task_omissions", "frontier_membership_counts_of_ten_omissions",
    "omissions_with_changed_frontier", "verified_canonical_inference_sha256",
    "verified_provenance_receipt_sha256", "verified_input_sha256",
    "source_provenance_independently_recomputed",
}
OMISSION_FIELDS = {
    "omitted_task_id", "retained_task_count", "frontier", "dominated_by",
    "variant_means", "frontier_differs_from_full_sample",
}
METRICS = ("strict_support_rate", "treatment_cost_usd")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value: object, name: str) -> float:
    result = common._number(value, name)
    require(result >= 0, f"{name} must be nonnegative")
    return result


def same(actual: object, expected: float, name: str) -> None:
    require(math.isclose(number(actual, name), expected, rel_tol=0, abs_tol=1e-12),
            f"{name} differs from retained per-task source evidence")


def rows(raw: bytes, label: str, required: set[str],
         tasks: list[str]) -> dict[tuple[str, str], dict[str, str]]:
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
        header = reader.fieldnames
        require(header is not None and len(header) == len(set(header))
                and required <= set(header), f"{label} invalid CSV header")
        data = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"{label} invalid UTF-8 CSV") from exc
    expected = {(v, t) for v in VARIANTS for t in tasks}
    indexed = {}
    for row in data:
        require(None not in row and all(item is not None for item in row.values()),
                f"{label} missing or extra columns")
        key = (row["variant_id"], row["task_id"])
        require(key in expected and key not in indexed,
                f"{label} unexpected or duplicate treatment/task cell")
        indexed[key] = row
    require(set(indexed) == expected, f"{label} incomplete 40-cell matrix")
    return indexed


def integer(raw: str, label: str) -> int:
    require(type(raw) is str and raw.isascii() and raw.isdecimal()
            and (raw == "0" or not raw.startswith("0")),
            f"{label} must be an exact nonnegative integer")
    return int(raw)


def frontier(means: dict[str, dict[str, float]]) -> dict:
    dominated = {v: [] for v in VARIANTS}
    for candidate in VARIANTS:
        for rival in VARIANTS:
            if rival == candidate:
                continue
            c, r = means[candidate], means[rival]
            if (r["strict_support_rate"] >= c["strict_support_rate"]
                    and r["treatment_cost_usd"] <= c["treatment_cost_usd"]
                    and (r["strict_support_rate"] > c["strict_support_rate"]
                         or r["treatment_cost_usd"] < c["treatment_cost_usd"])):
                dominated[candidate].append(rival)
    return {
        "frontier": [v for v in VARIANTS if not dominated[v]],
        "dominated_by": dominated,
    }


def compare_means(actual: object, expected: dict, label: str) -> None:
    require(type(actual) is dict and set(actual) == set(VARIANTS),
            f"{label} incomplete variant means")
    for v in VARIANTS:
        require(type(actual[v]) is dict and set(actual[v]) == set(METRICS),
                f"{label}/{v} invalid metric set")
        for metric in METRICS:
            same(actual[v][metric], expected[v][metric], f"{label}/{v}/{metric}")


def verify_bytes(inference_raw: bytes, provenance_raw: bytes, main_raw: bytes,
                 support_raw: bytes, diagnostic_raw: bytes) -> dict:
    inference = common._parse(inference_raw, "canonical inference")
    provenance = common._parse(provenance_raw, "execution-bound provenance")
    report = common._parse(diagnostic_raw, "Pareto diagnostic")
    require(type(provenance.get("verified_execution")) is dict,
            "provenance missing verified execution binding")
    hashes = {str(MAIN): hashlib.sha256(main_raw).hexdigest(),
              str(SUPPORT): hashlib.sha256(support_raw).hexdigest()}
    items = provenance.get("verified_inputs")
    require(type(items) is list and len(items) == 2
            and all(type(i) is dict for i in items)
            and {i.get("path"): i.get("sha256") for i in items} == hashes,
            "verified provenance input hashes not bound to retained CSV bytes")
    tasks = inference.get("task_ids")
    require(type(inference.get("schema_version")) is int
            and inference["schema_version"] == 1
            and inference.get("study_id") == "budget-main-v1"
            and inference.get("primary_outcome") == "strict_support_rate"
            and type(inference.get("n_tasks")) is int
            and inference["n_tasks"] == 10
            and type(tasks) is list and len(tasks) == 10
            and all(type(t) is str and t and t == t.strip() for t in tasks)
            and len(set(tasks)) == 10,
            "unexpected frozen task/study identity")
    require(set(report) == FIELDS
            and type(report.get("schema_version")) is int
            and report["schema_version"] == 1
            and report.get("study_id") == "budget-main-v1"
            and report.get("status") == "post_hoc_exploratory_pareto_stability_only"
            and report.get("confirmatory_analysis_replaced") is False
            and report.get("human_validation_performed") is False
            and report.get("inferential_p_values_or_intervals_added") is False
            and report.get("source_provenance_independently_recomputed") is True,
            "exploratory-only Pareto identity or claim invalid")
    require(report.get("task_ids") == tasks,
            "omission task order differs from frozen tasks")
    require(report.get("verified_canonical_inference_sha256") ==
            hashlib.sha256(inference_raw).hexdigest()
            and report.get("verified_provenance_receipt_sha256") ==
            hashlib.sha256(provenance_raw).hexdigest()
            and report.get("verified_input_sha256") == hashes,
            "diagnostic source bytes not exactly bound")
    main = rows(main_raw, "treatment", {
        "variant_id", "task_id", "completed", "treatment_cost_usd",
        "posthoc_claims_checked", "posthoc_strict_support_rate",
    }, tasks)
    support = rows(support_raw, "evaluator", {
        "variant_id", "task_id", "claims_checked", "supported",
        "partially_supported", "unsupported", "contradicted", "strict_support_rate",
    }, tasks)
    values = {}
    for v in VARIANTS:
        for t in tasks:
            m, s = main[v, t], support[v, t]
            counts = [integer(s[k], f"{v}/{t}/{k}") for k in (
                "claims_checked", "supported", "partially_supported",
                "unsupported", "contradicted",
            )]
            claims = counts[0]
            require(0 < claims <= 12 and sum(counts[1:]) == claims,
                    f"{v}/{t} evaluator counts inconsistent")
            support_rate = counts[1] / claims
            require(m["completed"] == "True"
                    and integer(m["posthoc_claims_checked"], "treatment claims") == claims,
                    f"{v}/{t} treatment/evaluator inconsistent")
            same(float(s["strict_support_rate"]), support_rate,
                 f"{v}/{t} evaluator rate")
            same(float(m["posthoc_strict_support_rate"]), support_rate,
                 f"{v}/{t} treatment rate")
            cost = number(float(m["treatment_cost_usd"]), f"{v}/{t} treatment cost")
            values[v, t] = (support_rate, cost)

    def means(kept: list[str]) -> dict[str, dict[str, float]]:
        return {v: {metric: statistics.mean(values[v, t][i] for t in kept)
                    for i, metric in enumerate(METRICS)} for v in VARIANTS}

    original = means(tasks)
    published = inference.get("variant_summary")
    require(type(published) is dict and set(published) == set(VARIANTS),
            "canonical variant family invalid")
    for v in VARIANTS:
        block = published[v]
        require(type(block) is dict and type(block.get("n")) is int
                and block["n"] == 10 and type(block.get("means")) is dict,
                "canonical variant denominator invalid")
        for metric in METRICS:
            same(block["means"].get(metric), original[v][metric],
                 f"canonical/{v}/{metric}")
    frozen_frontier = frontier(original)
    canonical_frontier = inference.get("cost_quality_pareto")
    require(type(canonical_frontier) is dict
            and canonical_frontier.get("frontier") == frozen_frontier["frontier"]
            and canonical_frontier.get("dominated_by") == frozen_frontier["dominated_by"],
            "canonical Pareto frontier inconsistent")
    compare_means(report.get("full_sample_variant_means"), original, "full-sample")
    require(report.get("full_sample_frontier") == frozen_frontier["frontier"],
            "reported full-sample Pareto frontier incorrect")

    omissions = report.get("all_task_omissions")
    require(type(omissions) is list and len(omissions) == 10,
            "must enumerate all ten task omissions")
    membership = {v: 0 for v in VARIANTS}
    changed = 0
    for i, task in enumerate(tasks):
        entry = omissions[i]
        require(type(entry) is dict and set(entry) == OMISSION_FIELDS
                and entry.get("omitted_task_id") == task
                and type(entry.get("retained_task_count")) is int
                and entry["retained_task_count"] == 9,
                f"{task} omission missing, reordered or invalid denominator")
        computed_means = means(tasks[:i] + tasks[i + 1:])
        compare_means(entry.get("variant_means"), computed_means, f"{task}/omission")
        computed_frontier = frontier(computed_means)
        require(entry.get("frontier") == computed_frontier["frontier"]
                and entry.get("dominated_by") == computed_frontier["dominated_by"],
                f"{task} Pareto frontier/dominance not independently reproduced")
        changed_flag = computed_frontier["frontier"] != frozen_frontier["frontier"]
        require(entry.get("frontier_differs_from_full_sample") is changed_flag,
                f"{task} invalid frontier-change flag")
        changed += changed_flag
        for v in computed_frontier["frontier"]:
            membership[v] += 1
    reported_membership = report.get("frontier_membership_counts_of_ten_omissions")
    require(type(reported_membership) is dict
            and set(reported_membership) == set(VARIANTS)
            and all(type(reported_membership[v]) is int
                    and reported_membership[v] == membership[v] for v in VARIANTS),
            "frontier membership totals inconsistent")
    require(type(report.get("omissions_with_changed_frontier")) is int
            and report["omissions_with_changed_frontier"] == changed,
            "changed-frontier count inconsistent")
    return {
        "schema_version": 1,
        "status": "independently_verified_post_hoc_exploratory_pareto_only",
        "pareto_diagnostic_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
        "verified_canonical_inference_sha256": hashlib.sha256(inference_raw).hexdigest(),
        "verified_provenance_receipt_sha256": hashlib.sha256(provenance_raw).hexdigest(),
        "verified_input_sha256": hashes,
        "number_of_single_task_omissions": len(omissions),
        "omissions_with_changed_frontier": changed,
        "confirmatory_analysis_replaced": False,
        "human_validation_performed": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--diagnostic", type=Path, required=True)
    p.add_argument("--checkout-sha", required=True)
    p.add_argument("--receipt-implementation-commit", required=True)
    p.add_argument("--source-selection-commit", required=True)
    p.add_argument("--run-id", required=True)
    args = p.parse_args()
    try:
        raw = lambda path, label: common._read_regular_bounded(path, label=label)
        output = verify_bytes(
            raw(args.root / INFERENCE, "inference"),
            raw(args.root / PROVENANCE, "provenance"),
            raw(args.root / MAIN, "treatments"),
            raw(args.root / SUPPORT, "evaluator"),
            raw(args.diagnostic, "Pareto diagnostic"),
        )
        for name in ("checkout_sha", "receipt_implementation_commit",
                     "source_selection_commit"):
            value = getattr(args, name)
            require(len(value) == 40 and all(c in "0123456789abcdef" for c in value),
                    f"{name} invalid lowercase commit SHA")
        require(args.run_id.isdecimal() and int(args.run_id) > 0,
                "invalid workflow run ID")
        output.update({
            "checkout_sha": args.checkout_sha,
            "frozen_analysis_implementation_commit": args.receipt_implementation_commit,
            "original_source_selection_commit": args.source_selection_commit,
            "workflow_run_id": args.run_id,
        })
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SystemExit(f"PARETO ARTIFACT VERIFICATION: FAIL: {exc}") from exc
    print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
