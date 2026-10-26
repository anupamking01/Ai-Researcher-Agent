"""Synthetic offline evidence for counterbalanced handoff-to-submission custody.

Every rating and report in this file is synthetic; no humans were evaluated.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_human_eval_packet as build
from scripts import export_human_eval_annotator_bundle as exporter
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_counterbalanced_submission_pair as pair


def _submission(root: Path, bundle: Path, identity: str) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    rating = root / ("rating-" + bundle.name + ".csv")
    rows = exporter._read_jsonl_packet((bundle / "packet.jsonl").read_bytes())
    with rating.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=freeze.RATING_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({"annotator_id": identity, "blind_id": row["blind_id"],
                             **{field: "3" for field in freeze.SCORE_FIELDS}, "notes": ""})
    receipt_root = root / ("receipt-" + bundle.name)
    receipt = freeze.preflight_annotator_submission(rating, annotator_bundle_root=bundle)
    freeze.publish_preflight_receipt(receipt, receipt_root)
    return rating, receipt_root


@pytest.fixture
def case(tmp_path):
    tasks = [("main-01", "Synthetic question one?"),
             ("main-02", "Synthetic question two?")]
    manifest = tmp_path / "experiments" / "main_budget_tasks.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"task_set_id": "main-budget-v1-test",
        "frozen_before_execution": True,
        "tasks": [{"id": task, "question": question} for task, question in tasks]}))
    for task, question in tasks:
        for variant in build.EXPECTED_VARIANTS:
            run_id = f"{variant.lower()}-{task}"
            report = tmp_path / "outputs" / run_id / "research_report.md"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text("# Synthetic neutral research report\n\nEvidence text.\n")
            trace = tmp_path / "outputs" / "experiment_traces" / variant / (run_id + ".json")
            trace.parent.mkdir(parents=True, exist_ok=True)
            trace.write_text(json.dumps({
                "schema_version": 2,
                "experiment": {"variant_id": variant, "task_id": task,
                               "task_set_id": "main-budget-v1-test"},
                "trace": {"run_id": run_id, "variant_id": variant, "task_id": task,
                          "question": question, "completed": True,
                          "report_path": f"./outputs/{run_id}/research_report.pdf"},
            }))
    packet_root = tmp_path / "outputs" / "human_eval"
    build.build_packet(tmp_path / "outputs" / "experiment_traces", packet_root,
                       seed=20260925, task_manifest_path=manifest)
    canonical, reverse = tmp_path / "canonical", tmp_path / "reverse"
    for root, order in ((canonical, "canonical"), (reverse, "reverse")):
        exporter.export_annotator_bundle(packet_root=packet_root, output_root=root,
            task_manifest_path=manifest, repo_root=tmp_path, presentation_order=order)
    rating_c, receipt_c = _submission(tmp_path, canonical, "rater-alpha")
    rating_r, receipt_r = _submission(tmp_path, reverse, "rater-beta")
    return dict(packet_root=packet_root, canonical_root=canonical, reverse_root=reverse,
        canonical_submission=rating_c, reverse_submission=rating_r,
        canonical_receipt_root=receipt_c, reverse_receipt_root=receipt_r,
        expected_coordinator_manifest_sha256=hashlib.sha256(
            (packet_root / "manifest.json").read_bytes()).hexdigest(),
        expected_n_reports=8, task_manifest_path=manifest, repo_root=tmp_path)


def test_valid_pair_is_source_bound_and_receipt_is_score_free(case):
    result = pair.verify_counterbalanced_submission_pair(**case)
    assert result["status"] == "human_eval_counterbalanced_submissions_source_bound"
    assert result["n_reports"] == 8
    assert result["distinct_annotator_pseudonyms"] is True
    assert result["presentation_orders"] == ["canonical", "reverse"]
    assert result["submissions"]["canonical"]["submission_sha256"] == freeze.sha256_file(
        case["canonical_submission"])
    assert "rater-alpha" not in json.dumps(result)
    assert "rater-beta" not in json.dumps(result)
    assert "correctness_1_5" not in json.dumps(result)


def test_wrong_independent_manifest_pin_fails(case):
    case["expected_coordinator_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="independently pinned"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_replayed_receipt_for_other_submission_fails(case):
    case["reverse_receipt_root"] = case["canonical_receipt_root"]
    with pytest.raises(ValueError, match="distinct receipt directories"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_swapped_valid_receipt_roots_cannot_pass(case):
    case["reverse_receipt_root"], case["canonical_receipt_root"] = (
        case["canonical_receipt_root"], case["reverse_receipt_root"])
    with pytest.raises(ValueError, match="does not match"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_duplicate_submitted_file_is_not_two_independent_ratings(case):
    case["reverse_submission"] = case["canonical_submission"]
    with pytest.raises(ValueError, match="distinct rating files"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_duplicate_human_pseudonym_fails_even_with_two_valid_files(case):
    root = case["reverse_root"].parent
    rating, receipt = _submission(root / "dup", case["reverse_root"], "rater-alpha")
    case["reverse_submission"] = rating
    case["reverse_receipt_root"] = receipt
    with pytest.raises(ValueError, match="distinct annotators"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_unicode_casefold_pseudonyms_are_not_distinct(case):
    root = case["reverse_root"].parent
    rating_a, receipt_a = _submission(root / "unicode-a", case["canonical_root"], "Rater-É")
    rating_b, receipt_b = _submission(root / "unicode-b", case["reverse_root"], "rater-e\u0301")
    case.update(canonical_submission=rating_a, canonical_receipt_root=receipt_a,
                reverse_submission=rating_b, reverse_receipt_root=receipt_b)
    with pytest.raises(ValueError, match="distinct annotators"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_both_bundles_canonical_cannot_masquerade_as_counterbalanced(case):
    root = case["reverse_root"].parent
    duplicate = root / "canonical-copy"
    exporter.export_annotator_bundle(packet_root=case["packet_root"],
        output_root=duplicate, task_manifest_path=case["task_manifest_path"],
        repo_root=case["repo_root"], presentation_order="canonical")
    case["reverse_root"] = duplicate
    with pytest.raises(ValueError, match="expected presentation order"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_modified_submitted_rating_fails_against_retained_receipt(case):
    rating = case["reverse_submission"]
    rating.write_bytes(rating.read_bytes().replace(b",3,3,3,3,3,", b",4,4,4,4,4,", 1))
    with pytest.raises(ValueError, match="does not match"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_source_packet_tampering_fails_even_if_receipts_remain_intact(case):
    target = case["packet_root"] / "packet.jsonl"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError):
        pair.verify_counterbalanced_submission_pair(**case)


def test_report_count_mismatch_fails_closed(case):
    case["expected_n_reports"] = 40
    with pytest.raises(ValueError, match="expected report count"):
        pair.verify_counterbalanced_submission_pair(**case)


def test_verifier_does_not_modify_any_original_evidence(case):
    keys = [("packet_root", "manifest.json"), ("canonical_root", "packet.jsonl"),
            ("reverse_root", "packet.jsonl"),
            ("canonical_receipt_root", "preflight_receipt.json"),
            ("reverse_receipt_root", "preflight_receipt.json")]
    evidence = [case[key] / name for key, name in keys]
    evidence += [case["canonical_submission"], case["reverse_submission"]]
    before = [path.read_bytes() for path in evidence]
    pair.verify_counterbalanced_submission_pair(**case)
    assert [path.read_bytes() for path in evidence] == before
