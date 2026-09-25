"""Synthetic-only checks for pre-unblinding human-evaluation freeze verification.

No scores in this module are collected human ratings or experimental results.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts.verify_human_eval_freeze import verify_frozen_snapshot


def _write_ratings(path: Path, annotator: str, score: str = "3") -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(freeze.RATING_FIELDS))
        writer.writeheader()
        writer.writerow(
            {
                "annotator_id": annotator,
                "blind_id": "H001",
                "correctness_1_5": score,
                "completeness_1_5": "3",
                "source_quality_1_5": "4",
                "synthesis_reasoning_1_5": "4",
                "clarity_1_5": "3",
                "notes": "",
            }
        )
    return path


@pytest.fixture
def frozen_case(tmp_path: Path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(
        json.dumps(
            {
                "blind_id": "H001",
                "task_id": "main-01",
                "question": "Synthetic question",
                "report_markdown": "Synthetic report",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_text("# Synthetic frozen protocol\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("# Synthetic frozen assignment\n", encoding="utf-8")
    first = _write_ratings(tmp_path / "annotator-a.csv", "synthetic-a")
    second = _write_ratings(tmp_path / "annotator-b.csv", "synthetic-b")
    output = tmp_path / "frozen-v1"

    freeze.freeze_ratings(
        [first, second],
        packet_path=packet,
        protocol_path=protocol,
        assignment_plan_path=assignment,
        output_root=output,
    )
    return {
        "ratings": [first, second],
        "freeze_root": output,
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
    }


def _verify(case):
    return verify_frozen_snapshot(
        case["ratings"],
        freeze_root=case["freeze_root"],
        packet_path=case["packet_path"],
        protocol_path=case["protocol_path"],
        assignment_plan_path=case["assignment_plan_path"],
    )


def _rewrite_manifest(case, mutate):
    path = case["freeze_root"] / "freeze_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_verified_snapshot_recomputes_blinded_invariants(frozen_case):
    receipt = _verify(frozen_case)
    assert receipt == {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "blinded_human_ratings_verified",
        "blinding_key_used": False,
        "n_raw_rating_inputs": 2,
        "n_rows": 2,
        "n_annotators": 2,
        "n_blind_ids": 1,
        "requires_predeclared_multi_rater_statistic": False,
    }


def test_changed_raw_rating_is_rejected(frozen_case):
    first = frozen_case["ratings"][0]
    _write_ratings(first, "synthetic-a", score="4")
    with pytest.raises(ValueError, match="raw rating inputs"):
        _verify(frozen_case)


def test_changed_packet_is_rejected(frozen_case):
    frozen_case["packet_path"].write_text(
        json.dumps({"blind_id": "H999", "question": "Replacement"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="packet fingerprint|unknown blind_id"):
        _verify(frozen_case)


@pytest.mark.parametrize("which", ["protocol_path", "assignment_plan_path"])
def test_changed_frozen_plan_is_rejected(frozen_case, which):
    frozen_case[which].write_text("# Changed after freeze\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        _verify(frozen_case)


def test_tampered_frozen_ratings_are_rejected_even_if_manifest_hash_is_updated(frozen_case):
    frozen_path = frozen_case["freeze_root"] / "frozen_ratings.csv"
    with frozen_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["correctness_1_5"] = "4"
    with frozen_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(freeze.RATING_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    content = frozen_path.read_bytes()

    def mutate(manifest):
        manifest["frozen_ratings"]["bytes"] = len(content)
        manifest["frozen_ratings"]["sha256"] = hashlib.sha256(content).hexdigest()

    _rewrite_manifest(frozen_case, mutate)
    with pytest.raises(ValueError, match="normalized raw inputs"):
        _verify(frozen_case)


def test_tampered_agreement_is_rejected_even_if_manifest_hash_is_updated(frozen_case):
    agreement_path = frozen_case["freeze_root"] / "agreement.json"
    agreement = json.loads(agreement_path.read_text(encoding="utf-8"))
    agreement["pairwise"][0]["dimensions"]["correctness_1_5"]["raw_exact_agreement"] = 0.0
    agreement_path.write_text(json.dumps(agreement, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    content = agreement_path.read_bytes()

    def mutate(manifest):
        manifest["agreement"]["bytes"] = len(content)
        manifest["agreement"]["sha256"] = hashlib.sha256(content).hexdigest()

    _rewrite_manifest(frozen_case, mutate)
    with pytest.raises(ValueError, match="recomputed agreement"):
        _verify(frozen_case)


def test_manifest_summary_drift_is_rejected(frozen_case):
    _rewrite_manifest(
        frozen_case,
        lambda manifest: manifest["frozen_ratings"].__setitem__("n_rows", 999),
    )
    with pytest.raises(ValueError, match="frozen row count"):
        _verify(frozen_case)


def test_missing_output_is_rejected(frozen_case):
    (frozen_case["freeze_root"] / "agreement.json").unlink()
    with pytest.raises(ValueError, match="agreement output must be a regular file"):
        _verify(frozen_case)


def test_cli_reports_pass_without_unblinding(frozen_case):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_human_eval_freeze",
            *(str(path) for path in frozen_case["ratings"]),
            "--freeze-root",
            str(frozen_case["freeze_root"]),
            "--packet",
            str(frozen_case["packet_path"]),
            "--protocol",
            str(frozen_case["protocol_path"]),
            "--assignment-plan",
            str(frozen_case["assignment_plan_path"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0
    assert "HUMAN EVAL VERIFY: PASS (ratings remain blinded)" in result.stdout
    assert "variant_id" not in result.stdout
    assert "D3" not in result.stdout
    assert result.stderr == ""


def test_cli_failure_has_no_success_receipt_or_traceback(frozen_case):
    (frozen_case["freeze_root"] / "agreement.json").write_text("{}\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_human_eval_freeze",
            *(str(path) for path in frozen_case["ratings"]),
            "--freeze-root",
            str(frozen_case["freeze_root"]),
            "--packet",
            str(frozen_case["packet_path"]),
            "--protocol",
            str(frozen_case["protocol_path"]),
            "--assignment-plan",
            str(frozen_case["assignment_plan_path"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert "HUMAN EVAL VERIFY: FAIL" in result.stderr
    assert "Traceback" not in result.stderr
    assert "HUMAN EVAL VERIFY: PASS" not in result.stdout
