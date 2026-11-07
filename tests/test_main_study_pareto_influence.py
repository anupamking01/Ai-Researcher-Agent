"""Synthetic, offline evidence/robustness tests. Never generates research results."""
import copy
import csv
import hashlib
import io
import json

import pytest

from scripts import analyze_main_study_pareto_influence as audit


def _fixture():
    tasks = [f"task-{i:02d}" for i in range(10)]
    variants = audit.frozen.VARIANTS
    costs = {"D3": 0.1, "D6": 0.2, "P6": 0.3, "P6V": 0.4}
    strengths = {"D3": 6, "D6": 7, "P6": 3, "P6V": 2}
    scores = {}
    main = []
    support = []
    for variant in variants:
        for task in tasks:
            supported = (10 if variant == "D3" else 0) if task == tasks[0] and variant in {"D3", "D6"} else strengths[variant]
            scores[variant, task] = supported / 10
            main.append({
                "variant_id": variant, "task_id": task, "completed": "True",
                "treatment_cost_usd": str(costs[variant]),
                "posthoc_claims_checked": "10",
                "posthoc_strict_support_rate": str(supported / 10),
            })
            support.append({
                "variant_id": variant, "task_id": task, "claims_checked": "10",
                "supported": str(supported), "partially_supported": "0",
                "unsupported": str(10 - supported), "contradicted": "0",
                "strict_support_rate": str(supported / 10),
            })
    def write(rows):
        text = io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        return text.getvalue().encode()
    summary = {variant: {"n": 10, "means": {
        "strict_support_rate": sum(scores[variant, t] for t in tasks) / 10,
        "treatment_cost_usd": costs[variant],
    }} for variant in variants}
    analysis = {
        "schema_version": 1, "study_id": "budget-main-v1",
        "primary_outcome": "strict_support_rate", "n_tasks": 10,
        "task_ids": tasks, "variant_summary": summary,
        "primary_contrasts": {
            name: {"task_differences": [scores[right, t] - scores[left, t]
                                       for t in tasks]}
            for left, right, name in audit.frozen.PRIMARY_CONTRASTS
        },
        "cost_quality_pareto": audit.frozen._pareto_frontier(summary),
    }
    return analysis, write(main), write(support)


def test_all_task_omissions_and_cost_quality_frontier_shift_are_descriptive():
    args = _fixture()
    out = audit.diagnostic(*args)
    assert out["status"] == "post_hoc_exploratory_pareto_stability_only"
    assert out["confirmatory_analysis_replaced"] is False
    assert out["human_validation_performed"] is False
    assert out["inferential_p_values_or_intervals_added"] is False
    assert out["full_sample_frontier"] == ["D3"]
    assert [o["omitted_task_id"] for o in out["all_task_omissions"]] == args[0]["task_ids"]
    assert all(o["retained_task_count"] == 9 for o in out["all_task_omissions"])
    assert out["all_task_omissions"][0]["frontier"] == ["D3", "D6"]
    assert all(o["frontier"] == ["D3"] for o in out["all_task_omissions"][1:])
    assert out["omissions_with_changed_frontier"] == 1
    assert out["frontier_membership_counts_of_ten_omissions"] == {
        "D3": 10, "D6": 1, "P6": 0, "P6V": 0,
    }


def test_determinism_does_not_mutate_source_or_frozen_summary():
    args = _fixture()
    original = copy.deepcopy(args)
    assert audit.diagnostic(*args) == audit.diagnostic(*args)
    assert args == original


def test_wrong_canonical_cost_mean_fails_closed():
    analysis, main, support = _fixture()
    analysis["variant_summary"]["D6"]["means"]["treatment_cost_usd"] = 0.01
    with pytest.raises(ValueError, match="canonical mean"):
        audit.diagnostic(analysis, main, support)


def test_wrong_paired_task_values_fail_before_pareto_reporting():
    analysis, main, support = _fixture()
    first = next(iter(analysis["primary_contrasts"].values()))
    first["task_differences"][0] += 0.1
    with pytest.raises(ValueError, match="canonical paired differences"):
        audit.diagnostic(analysis, main, support)


def test_corrupt_published_full_frontier_fails_closed():
    analysis, main, support = _fixture()
    analysis["cost_quality_pareto"]["frontier"] = ["D6"]
    with pytest.raises(ValueError, match="frontier not canonical"):
        audit.diagnostic(analysis, main, support)


def _edit_csv(data, modify):
    reader = csv.DictReader(io.StringIO(data.decode(), newline=""))
    rows = list(reader)
    modify(rows)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


@pytest.mark.parametrize("which,modify,error", [
    ("support", lambda r: r.pop(), "incomplete frozen treatment matrix"),
    ("support", lambda r: r.append(copy.copy(r[0])), "duplicate"),
    ("support", lambda r: r[0].update(supported="8"), "claims/counts mismatch"),
    ("support", lambda r: r[0].update(claims_checked="8.0"), "exact non-negative integer"),
    ("support", lambda r: r[0].update(strict_support_rate="NaN"), "finite nonnegative"),
    ("main", lambda r: r[0].update(completed="False"), "not completed"),
    ("main", lambda r: r[0].update(treatment_cost_usd="inf"), "finite nonnegative"),
    ("main", lambda r: r[0].update(posthoc_claims_checked="9"), "claim-count mismatch"),
    ("main", lambda r: r[0].update(task_id="different-task"), "unexpected task/treatment"),
])
def test_adverse_or_missing_treatment_and_evaluation_cells_fail_closed(which, modify, error):
    analysis, main, support = _fixture()
    if which == "main":
        main = _edit_csv(main, modify)
    else:
        support = _edit_csv(support, modify)
    with pytest.raises(ValueError, match=error):
        audit.diagnostic(analysis, main, support)


def test_duplicate_csv_header_fails_closed():
    analysis, main, support = _fixture()
    bad = main.replace(b"variant_id,task_id,", b"variant_id,variant_id,", 1)
    with pytest.raises(ValueError, match="header missing or ambiguous"):
        audit.diagnostic(analysis, bad, support)


def test_verified_wrapper_rejects_unbound_input_hashes(tmp_path, monkeypatch):
    analysis, main, support = _fixture()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "main_study_runs.csv").write_bytes(main)
    (outputs / "posthoc_support_runs.csv").write_bytes(support)
    inference = json.dumps(analysis).encode()
    (outputs / "main_study_inference.json").write_bytes(inference)
    receipt = {"verified_inputs": [
        {"path": str(audit.MAIN), "sha256": "0" * 64},
        {"path": str(audit.SUPPORT), "sha256": hashlib.sha256(support).hexdigest()},
    ]}
    receipt_bytes = json.dumps(receipt).encode()
    (outputs / "main_study_analysis_provenance.json").write_bytes(receipt_bytes)
    monkeypatch.setattr(audit.custody, "run_verified", lambda root: {
        "verified_canonical_inference_sha256": hashlib.sha256(inference).hexdigest(),
        "verified_provenance_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    })
    with pytest.raises(ValueError, match="not bound to verified provenance"):
        audit.run_verified(tmp_path)


def test_verified_wrapper_detects_source_mutation_during_upstream_gate(tmp_path, monkeypatch):
    analysis, main, support = _fixture()
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    main_file = outputs / "main_study_runs.csv"
    main_file.write_bytes(main)
    (outputs / "posthoc_support_runs.csv").write_bytes(support)
    (outputs / "main_study_inference.json").write_text(json.dumps(analysis))
    (outputs / "main_study_analysis_provenance.json").write_text("{}")
    def modify(_):
        main_file.write_bytes(main + b"\n")
        return {}
    monkeypatch.setattr(audit.custody, "run_verified", modify)
    with pytest.raises(ValueError, match="changed during Pareto audit"):
        audit.run_verified(tmp_path)
