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
    ("malformed_preflight_hash", "canonical submission receipt values invalid"),
    ("omitted_preflight_hash", "canonical submission receipt schema mismatch"),
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
    elif mutation == "malformed_preflight_hash":
        proof["submissions"]["canonical"]["preflight_receipt_sha256"] = "not-a-sha256"
    elif mutation == "omitted_preflight_hash":
        del proof["submissions"]["canonical"]["preflight_receipt_sha256"]
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
    altered = proof.replace(
        '"schema_version": 2,', '"schema_version": 2, "schema_version": 2,', 1
    )
    assert altered != proof  # Fail if a future schema change makes this a no-op.
    path.write_text(altered)
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


def test_oversized_pair_receipt_is_refused_before_any_content_read(tmp_path, monkeypatch):
    """A 64-KiB provenance record must not consume the 64-MiB ratings allowance."""
    source = tmp_path / "oversized-pair-receipt.json"
    source.write_bytes(b" " * (link.MAX_RECEIPT_BYTES + 1))

    def unexpected_read(*args, **kwargs):
        raise AssertionError("oversized pair receipt was read")

    monkeypatch.setattr(freeze.os, "pread", unexpected_read)
    with pytest.raises(ValueError, match=f"pair receipt exceeds {link.MAX_RECEIPT_BYTES} byte"):
        link._pinned_pair(source, "0" * 64)


def test_pair_receipt_capture_exact_limit_and_concurrent_growth_gate(tmp_path, monkeypatch):
    source = tmp_path / "limit-receipt.json"
    original = b"x" * link.MAX_RECEIPT_BYTES
    source.write_bytes(original)
    assert freeze._capture_regular_input(
        source, label="pair receipt", max_bytes=link.MAX_RECEIPT_BYTES
    ) == original

    # A file initially within the limit must still fail if it grows in
    # the bounded descriptor observation window.
    real_pread = freeze.os.pread
    changed = False

    def grow_during_capture(fd, size, offset):
        nonlocal changed
        data = real_pread(fd, size, offset)
        if not changed:
            changed = True
            with source.open("ab") as destination:
                destination.write(b"y")
        return data

    monkeypatch.setattr(freeze.os, "pread", grow_during_capture)
    with pytest.raises(ValueError, match="grew while it was being read|changed while it was being read"):
        freeze._capture_regular_input(
            source, label="pair receipt", max_bytes=link.MAX_RECEIPT_BYTES
        )


@pytest.mark.parametrize("invalid_limit", [True, 0, -1, 1.0, freeze.MAX_HUMAN_FREEZE_INPUT_BYTES + 1])
def test_capture_rejects_invalid_caller_specific_resource_limits(tmp_path, invalid_limit):
    source = tmp_path / "tiny-receipt.json"
    source.write_bytes(b"{}")
    with pytest.raises(ValueError, match="capture limit"):
        freeze._capture_regular_input(source, label="pair receipt", max_bytes=invalid_limit)


def test_recheck_rejects_receipt_expanded_above_limit_before_read(frozen_case, monkeypatch):
    """The end-of-audit recheck must not fall back to the 64-MiB CSV limit."""
    original_verify = link.freeze_verify.verify_frozen_snapshot
    real_pread = freeze.os.pread

    def expand_after_archive_verification(*args, **kwargs):
        result = original_verify(*args, **kwargs)
        frozen_case["pair_receipt_path"].write_bytes(
            b" " * (link.MAX_RECEIPT_BYTES + 1)
        )

        def assert_no_oversized_read(fd, size, offset):
            if freeze.os.fstat(fd).st_size > link.MAX_RECEIPT_BYTES:
                raise AssertionError("oversized recheck read receipt payload")
            return real_pread(fd, size, offset)

        monkeypatch.setattr(freeze.os, "pread", assert_no_oversized_read)
        return result

    monkeypatch.setattr(
        link.freeze_verify, "verify_frozen_snapshot", expand_after_archive_verification
    )
    with pytest.raises(
        ValueError,
        match=f"pair receipt recheck exceeds {link.MAX_RECEIPT_BYTES} byte",
    ):
        link.verify_counterbalanced_freeze_link(**frozen_case)


def test_deeply_nested_pinned_receipt_fails_with_controlled_error(tmp_path):
    """An independently pinned but malformed JSON receipt must not crash the CLI."""
    source = tmp_path / "nested-pair-receipt.json"
    source.write_bytes(b"[" * 2000 + b"0" + b"]" * 2000)
    pinned = hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="pair receipt JSON nesting"):
        link._pinned_pair(source, pinned)
