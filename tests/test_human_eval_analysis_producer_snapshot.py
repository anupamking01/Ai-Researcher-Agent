"""Synthetic regression tests for snapshot-bound freeze-producer provenance.

No real human annotations, treatment mapping, or experimental results are
created. The tests stop at the blinded gate before any unblinding step.
"""
import csv
import json

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import human_eval_analysis_core as analysis


class EndOfBlindedGate(Exception):
    """Stop the synthetic test before treatment identity can be accessed."""


@pytest.fixture
def case(tmp_path):
    packet_root = tmp_path / "human_eval"
    packet_root.mkdir()
    packet = packet_root / "packet.jsonl"
    packet.write_text(
        json.dumps({
            "blind_id": "H001",
            "question": "Synthetic question",
            "report_markdown": "Synthetic report",
        }) + "\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_text("# Synthetic protocol\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("# Synthetic assignment\n", encoding="utf-8")
    analysis_plan = tmp_path / "analysis_plan.md"
    analysis_plan.write_text("# Synthetic analysis plan\n", encoding="utf-8")
    rating_paths = []
    for annotator in ("synthetic-a", "synthetic-b"):
        ratings = tmp_path / f"{annotator}.csv"
        with ratings.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=freeze.RATING_FIELDS)
            writer.writeheader()
            writer.writerow({
                "annotator_id": annotator,
                "blind_id": "H001",
                **{field: "3" for field in freeze.SCORE_FIELDS},
                "notes": "",
            })
        rating_paths.append(ratings)
    freeze_root = packet_root / "frozen-v1"
    freeze.freeze_ratings(
        rating_paths,
        packet_path=packet,
        protocol_path=protocol,
        assignment_plan_path=assignment,
        output_root=freeze_root,
    )
    return {
        "rating_paths": rating_paths,
        "freeze_root": freeze_root,
        "packet_root": packet_root,
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "analysis_plan_path": analysis_plan,
        "repo_root": tmp_path,
    }


def _analyze(case):
    return analysis.analyze(
        case["rating_paths"],
        **{key: value for key, value in case.items() if key != "rating_paths"},
    )


def test_producer_snapshot_verified_even_if_source_changes_after_capture(case, monkeypatch):
    producer = case["freeze_root"] / "provenance" / "freeze_human_eval_ratings.py"
    original = producer.read_bytes()
    real_verify = analysis.blind_verify.verify_frozen_snapshot
    seen = {}

    def verify_then_stop(*args, **kwargs):
        archive = kwargs["freeze_root"] / "provenance" / "freeze_human_eval_ratings.py"
        seen["snapshot"] = archive.read_bytes()
        producer.write_bytes(b"# Synthetic modification after snapshot\n")
        seen["receipt"] = real_verify(*args, **kwargs)
        raise EndOfBlindedGate()

    monkeypatch.setattr(analysis.blind_verify, "verify_frozen_snapshot", verify_then_stop)
    with pytest.raises(EndOfBlindedGate):
        _analyze(case)
    assert seen["receipt"]["status"] == "blinded_human_ratings_verified"
    assert seen["snapshot"] == original
    assert producer.read_bytes() != original


def test_tampered_producer_rejected_before_unblinding(case):
    producer = case["freeze_root"] / "provenance" / "freeze_human_eval_ratings.py"
    producer.write_bytes(producer.read_bytes() + b"\n# synthetic tamper\n")
    with pytest.raises(ValueError, match="archived freeze producer fingerprint"):
        _analyze(case)


def test_symlinked_producer_is_not_laundered_into_snapshot(case):
    producer = case["freeze_root"] / "provenance" / "freeze_human_eval_ratings.py"
    original = producer.read_bytes()
    producer.unlink()
    alternative = case["freeze_root"] / "other.py"
    alternative.write_bytes(original)
    producer.symlink_to(alternative)
    with pytest.raises(ValueError, match="blinded freeze producer must be a regular file"):
        _analyze(case)
