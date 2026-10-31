"""Synthetic tests: no actual human annotators or outcomes."""
from __future__ import annotations

import hashlib
import json

import pytest

from human_eval_test_support import write_valid_annotator_attestations
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_counterbalanced_submission_pair as pair
from scripts import verify_human_eval_counterbalanced_freeze_link as link
from test_human_eval_counterbalanced_submission_pair import case


@pytest.fixture
def frozen_case(case, tmp_path):
    proof = pair.verify_counterbalanced_submission_pair(**case)
    proof_path = tmp_path / "pair-receipt.json"
    proof_path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    attest = write_valid_annotator_attestations(
        tmp_path / "attestations.csv", ["rater-alpha", "rater-beta"]
    )
    frozen_root = tmp_path / "frozen"
    freeze.freeze_ratings(
        [case["canonical_submission"], case["reverse_submission"]],
        submission_preflights=[
            (case["canonical_receipt_root"], case["canonical_root"]),
            (case["reverse_receipt_root"], case["reverse_root"]),
        ],
        annotator_attestations_path=attest,
        packet_path=case["packet_root"] / "packet.jsonl",
        output_root=frozen_root,
    )
    return {
        "freeze_root": frozen_root,
        "pair_receipt_path": proof_path,
        "expected_pair_receipt_sha256": hashlib.sha256(proof_path.read_bytes()).hexdigest(),
        "expected_n_reports": 8,
    }


def test_pair_exactly_matches_blinded_archive_without_revealing_scores(frozen_case):
    result = link.verify_counterbalanced_freeze_link(**frozen_case)
    assert result["status"] == "counterbalanced_pair_bound_to_verified_blinded_freeze"
    assert result["both_presentation_orders_preserved"] is True
    assert result["n_reports"] == 8
    assert "rater-alpha" not in json.dumps(result)
    assert "rater-beta" not in json.dumps(result)
    assert "correctness_1_5" not in json.dumps(result)


def test_wrong_external_digest_is_rejected(frozen_case):
    frozen_case["expected_pair_receipt_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="independent SHA-256"):
        link.verify_counterbalanced_freeze_link(**frozen_case)


@pytest.mark.parametrize("mutation, message", [
    ("canonical_sha", "canonical archived raw rating"),
    ("reverse_sha", "reverse archived raw rating"),
    ("reverse_bundle", "reverse retained preflight"),
    ("missing_count", "reverse retained preflight"),
    ("same_order", "counterbalance contract"),
    ("wrong_report_count", "report count"),
])
def test_reject_false_pre_freeze_claim_even_if_digest_repinned(frozen_case, mutation, message):
    path = frozen_case["pair_receipt_path"]
    proof = json.loads(path.read_text())
    if mutation == "canonical_sha":
        proof["submissions"]["canonical"]["submission_sha256"] = "0" * 64
    elif mutation == "reverse_sha":
        proof["submissions"]["reverse"]["submission_sha256"] = "0" * 64
    elif mutation == "reverse_bundle":
        proof["submissions"]["reverse"]["annotator_manifest_sha256"] = "0" * 64
    elif mutation == "missing_count":
        proof["submissions"]["reverse"]["n_missing_dimension_values"] = 1
    elif mutation == "same_order":
        proof["presentation_orders"] = ["canonical", "canonical"]
    else:
        proof["n_reports"] = 40
        for order in ("canonical", "reverse"):
            proof["submissions"][order]["n_reports"] = 40
    path.write_text(json.dumps(proof, sort_keys=True))
    frozen_case["expected_pair_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match=message):
        link.verify_counterbalanced_freeze_link(**frozen_case)


def test_duplicate_json_key_is_rejected(frozen_case):
    path = frozen_case["pair_receipt_path"]
    proof = path.read_text()
    path.write_text(proof.replace(
        '"schema_version": 1,', '"schema_version": 1, "schema_version": 1,', 1
    ))
    frozen_case["expected_pair_receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="duplicate JSON key"):
        link.verify_counterbalanced_freeze_link(**frozen_case)


def test_corrupted_raw_rating_archive_is_rejected(frozen_case):
    path = frozen_case["freeze_root"] / "raw_rating_inputs" / "0001.csv"
    path.write_bytes(path.read_bytes() + b"extra\n")
    with pytest.raises(ValueError):
        link.verify_counterbalanced_freeze_link(**frozen_case)


def test_missing_preflights_does_not_inherit_pair_provenance(case, tmp_path):
    attest = write_valid_annotator_attestations(
        tmp_path / "attestations.csv", ["rater-alpha", "rater-beta"]
    )
    frozen_root = tmp_path / "frozen_without_preflights"
    freeze.freeze_ratings(
        [case["canonical_submission"], case["reverse_submission"]],
        annotator_attestations_path=attest,
        packet_path=case["packet_root"] / "packet.jsonl",
        output_root=frozen_root,
    )
    proof = pair.verify_counterbalanced_submission_pair(**case)
    path = tmp_path / "pair-receipt.json"
    path.write_text(json.dumps(proof, sort_keys=True))
    with pytest.raises(ValueError, match="exactly two archived"):
        link.verify_counterbalanced_freeze_link(
            freeze_root=frozen_root, pair_receipt_path=path,
            expected_pair_receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            expected_n_reports=8,
        )


def test_pair_receipt_changed_mid_verification_rejected(frozen_case, monkeypatch):
    original = link.freeze_verify.verify_frozen_snapshot

    def mutate(*args, **kwargs):
        result = original(*args, **kwargs)
        path = frozen_case["pair_receipt_path"]
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(link.freeze_verify, "verify_frozen_snapshot", mutate)
    with pytest.raises(ValueError, match="pair receipt changed during"):
        link.verify_counterbalanced_freeze_link(**frozen_case)
