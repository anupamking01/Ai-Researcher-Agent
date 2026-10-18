"""Synthetic checks for treatment-blind annotator submission preflight."""
from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import export_human_eval_annotator_bundle as exporter
from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_submission_preflight as verify


def _write_bundle(root: Path) -> Path:
    root.mkdir()
    packet_rows = [
        {
            "blind_id": "H001",
            "task_id": "main-01",
            "question": "Synthetic question one?",
            "report_markdown": "# Synthetic report one",
        },
        {
            "blind_id": "H002",
            "task_id": "main-02",
            "question": "Synthetic question two?",
            "report_markdown": "# Synthetic report two",
        },
    ]
    packet_bytes = (
        "\n".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True)
            for row in packet_rows
        )
        + "\n"
    ).encode("utf-8")
    (root / "packet.jsonl").write_bytes(packet_bytes)

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(exporter.build.RATING_FIELDS))
    writer.writeheader()
    for row in packet_rows:
        writer.writerow({"blind_id": row["blind_id"]})
    template_bytes = output.getvalue().encode("utf-8")
    (root / "ratings_template.csv").write_bytes(template_bytes)

    guide_bytes = exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes()
    (root / "annotator_instructions.md").write_bytes(guide_bytes)
    manifest = {
        "schema_version": 2,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
        "presentation_order": "canonical",
        "n_reports": len(packet_rows),
        "content_validator": exporter._content_validator_source_contract(),
        "content_validator_runtime": (
            exporter.build.content_validator_runtime_contract()
        ),
        "artifacts": {
            "packet": {"path": "packet.jsonl", **exporter._fingerprint(packet_bytes)},
            "ratings_template": {
                "path": "ratings_template.csv",
                **exporter._fingerprint(template_bytes),
            },
            "annotator_instructions": {
                "path": "annotator_instructions.md",
                **exporter._fingerprint(guide_bytes),
            },
        },
        "distribution_note": exporter.DISTRIBUTION_NOTE,
    }
    (root / "annotator_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return root


def _rating_row(annotator_id: str, blind_id: str, *, score: str = "4") -> dict:
    return {
        "annotator_id": annotator_id,
        "blind_id": blind_id,
        **{field: score for field in freeze.SCORE_FIELDS},
        "notes": "",
    }


def _write_submission(path: Path, rows: list[dict], *, extra_fields=()) -> Path:
    fieldnames = [*freeze.RATING_FIELDS, *extra_fields]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _published_receipt(tmp_path: Path) -> tuple[Path, Path, Path]:
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    receipt = freeze.preflight_annotator_submission(
        submission,
        annotator_bundle_root=bundle,
    )
    receipt_root = tmp_path / "preflight-receipt"
    freeze.publish_preflight_receipt(receipt, receipt_root)
    return receipt_root, submission, bundle


def test_preflight_accepts_one_complete_blinded_submission(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )

    receipt = freeze.preflight_annotator_submission(
        submission,
        annotator_bundle_root=bundle,
    )

    assert receipt == {
        "schema_version": 2,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_submission_verified",
        "annotator_id": "ann-a",
        "n_reports": 2,
        "n_missing_dimension_values": 0,
        "presentation_order": "canonical",
        "submission": {
            "name": "ann-a.csv",
            "bytes": submission.stat().st_size,
            "sha256": freeze.sha256_file(submission),
        },
        "annotator_manifest_sha256": freeze.sha256_file(
            bundle / "annotator_manifest.json"
        ),
        "packet_sha256": freeze.sha256_file(bundle / "packet.jsonl"),
        "ratings_template_sha256": freeze.sha256_file(
            bundle / "ratings_template.csv"
        ),
        "annotator_guide_sha256": freeze.sha256_file(
            bundle / "annotator_instructions.md"
        ),
    }


def test_preflight_rejects_partial_submission(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001")],
    )

    with pytest.raises(ValueError, match="cover every blinded report"):
        freeze.preflight_annotator_submission(
            submission,
            annotator_bundle_root=bundle,
        )


def test_preflight_rejects_mixed_annotator_ids(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "mixed.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-b", "H002")],
    )

    with pytest.raises(ValueError, match="exactly one annotator_id"):
        freeze.preflight_annotator_submission(
            submission,
            annotator_bundle_root=bundle,
        )


@pytest.mark.parametrize(
    ("rows", "extra_fields", "message"),
    [
        (
            [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
            ("variant_id",),
            "must stay blinded",
        ),
        (
            [_rating_row("ann-a", "H001", score="6"), _rating_row("ann-a", "H002")],
            (),
            "outside the 1-5 rubric",
        ),
    ],
)
def test_preflight_reuses_frozen_schema_and_score_contract(
    tmp_path, rows, extra_fields, message
):
    bundle = _write_bundle(tmp_path / "bundle")
    for row in rows:
        for field in extra_fields:
            row[field] = "P6V"
    submission = _write_submission(
        tmp_path / "invalid.csv",
        rows,
        extra_fields=extra_fields,
    )

    with pytest.raises(ValueError, match=message):
        freeze.preflight_annotator_submission(
            submission,
            annotator_bundle_root=bundle,
        )


def test_preflight_never_reads_coordinator_blinding_key(tmp_path, monkeypatch):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    (tmp_path / "blinding_key.csv").write_text(
        "blind_id,variant_id\nH001,P6V\n",
        encoding="utf-8",
    )
    real_read_bytes = Path.read_bytes

    def reject_key_read(path):
        if path.name == "blinding_key.csv":
            raise AssertionError("annotator preflight must not read the blinding key")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_key_read)

    receipt = freeze.preflight_annotator_submission(
        submission,
        annotator_bundle_root=bundle,
    )
    assert receipt["status"] == "human_eval_annotator_submission_verified"


def test_preflight_rejects_symlinked_ratings_submission(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    original = _write_submission(
        tmp_path / "original.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    submission = tmp_path / "linked.csv"
    submission.symlink_to(original)

    with pytest.raises(ValueError, match="ratings input 1 must be a regular file"):
        freeze.preflight_annotator_submission(
            submission,
            annotator_bundle_root=bundle,
        )


def test_preflight_rejects_ratings_path_replacement_during_capture(
    tmp_path, monkeypatch
):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    displaced = tmp_path / "displaced.csv"
    initial = submission.stat()
    target = (initial.st_dev, initial.st_ino)
    real_pread = freeze.os.pread
    replacements = []

    def replace_after_read(file_descriptor, size, offset):
        content = real_pread(file_descriptor, size, offset)
        opened = freeze.os.fstat(file_descriptor)
        if content and not replacements and (opened.st_dev, opened.st_ino) == target:
            submission.rename(displaced)
            _write_submission(
                submission,
                [
                    _rating_row("ann-a", "H001", score="3"),
                    _rating_row("ann-a", "H002", score="3"),
                ],
            )
            replacements.append(True)
        return content

    monkeypatch.setattr(freeze.os, "pread", replace_after_read)

    with pytest.raises(ValueError, match="changed while it was being read"):
        freeze.preflight_annotator_submission(
            submission,
            annotator_bundle_root=bundle,
        )
    assert replacements == [True]


def test_preflight_cli_prints_blinded_receipt_without_writing_outputs(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    output_root = tmp_path / "must-not-exist"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.freeze_human_eval_ratings",
            str(submission),
            "--preflight-bundle",
            str(bundle),
            "--output-root",
            str(output_root),
        ],
        cwd=freeze.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "HUMAN EVAL SUBMISSION PREFLIGHT: PASS (ratings remain blinded)" in (
        completed.stdout
    )
    assert '"status": "human_eval_annotator_submission_verified"' in (
        completed.stdout
    )
    assert not output_root.exists()


def test_preflight_cli_can_publish_create_only_receipt(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    receipt_root = tmp_path / "preflight-receipt"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.freeze_human_eval_ratings",
            str(submission),
            "--preflight-bundle",
            str(bundle),
            "--preflight-receipt-root",
            str(receipt_root),
        ],
        cwd=freeze.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    retained = json.loads(
        (receipt_root / "preflight_receipt.json").read_text(encoding="utf-8")
    )
    assert retained == freeze.preflight_annotator_submission(
        submission,
        annotator_bundle_root=bundle,
    )
    assert retained["presentation_order"] == "canonical"
    assert retained["submission"]["sha256"] == freeze.sha256_file(submission)
    assert "HUMAN EVAL SUBMISSION PREFLIGHT: PASS (ratings remain blinded)" in (
        completed.stdout
    )


def test_preflight_receipt_publication_refuses_existing_destination(tmp_path):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    receipt = freeze.preflight_annotator_submission(
        submission,
        annotator_bundle_root=bundle,
    )
    receipt_root = tmp_path / "existing"
    receipt_root.mkdir()
    marker = receipt_root / "keep.txt"
    marker.write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.publish_preflight_receipt(receipt, receipt_root)

    assert marker.read_text(encoding="utf-8") == "preserve me\n"
    assert not (receipt_root / "preflight_receipt.json").exists()


def test_preflight_receipt_option_requires_preflight_bundle(tmp_path):
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.freeze_human_eval_ratings",
            str(submission),
            "--preflight-receipt-root",
            str(tmp_path / "receipt"),
        ],
        cwd=freeze.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "requires --preflight-bundle" in completed.stderr


def test_independent_cli_verifies_retained_preflight_receipt(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_human_eval_submission_preflight",
            "--receipt-root",
            str(receipt_root),
            "--ratings",
            str(submission),
            "--preflight-bundle",
            str(bundle),
        ],
        cwd=freeze.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (
        "HUMAN EVAL SUBMISSION RECEIPT VERIFY: PASS (ratings remain blinded)"
        in completed.stdout
    )


def test_receipt_verifier_rejects_duplicate_json_keys(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    receipt_path = receipt_root / verify.RECEIPT_NAME
    content = receipt_path.read_text(encoding="utf-8")
    receipt_path.write_text(
        content.replace(
            '  "schema_version": 2,',
            '  "schema_version": 2,\n  "schema_version": 2,',
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate key"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_undeclared_directory_entry(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    (receipt_root / "untracked.txt").write_text("unexpected\n", encoding="utf-8")

    with pytest.raises(ValueError, match="artifact set"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_symlinked_receipt_root(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    linked_root = tmp_path / "linked-receipt"
    linked_root.symlink_to(receipt_root, target_is_directory=True)

    with pytest.raises(ValueError, match="regular directory"):
        verify.verify_preflight_receipt(
            receipt_root=linked_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_symlinked_receipt_file(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    receipt_path = receipt_root / verify.RECEIPT_NAME
    displaced_receipt = tmp_path / "displaced-receipt.json"
    receipt_path.rename(displaced_receipt)
    receipt_path.symlink_to(displaced_receipt)

    with pytest.raises(ValueError, match="regular file"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_boolean_in_integer_field(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    receipt_path = receipt_root / verify.RECEIPT_NAME
    retained = json.loads(receipt_path.read_text(encoding="utf-8"))
    retained["n_missing_dimension_values"] = False
    receipt_path.write_text(
        json.dumps(retained, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_preflight_cli_requires_successful_independent_receipt_readback(
    tmp_path, monkeypatch
):
    bundle = _write_bundle(tmp_path / "bundle")
    submission = _write_submission(
        tmp_path / "ann-a.csv",
        [_rating_row("ann-a", "H001"), _rating_row("ann-a", "H002")],
    )
    receipt_root = tmp_path / "corrupt-receipt"

    def publish_corrupt_receipt(receipt, output_root):
        output_root.mkdir()
        corrupt = dict(receipt)
        corrupt["annotator_id"] = "substituted"
        (output_root / verify.RECEIPT_NAME).write_text(
            json.dumps(corrupt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return output_root / verify.RECEIPT_NAME

    monkeypatch.setattr(freeze, "publish_preflight_receipt", publish_corrupt_receipt)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "freeze_human_eval_ratings.py",
            str(submission),
            "--preflight-bundle",
            str(bundle),
            "--preflight-receipt-root",
            str(receipt_root),
        ],
    )

    with pytest.raises(SystemExit, match="does not match"):
        freeze.main()


def test_receipt_verifier_rejects_submission_substitution(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    _write_submission(
        submission,
        [_rating_row("ann-a", "H001", score="3"), _rating_row("ann-a", "H002")],
    )

    with pytest.raises(ValueError, match="does not match"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_receipt_hash_tampering(tmp_path):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    receipt_path = receipt_root / verify.RECEIPT_NAME
    retained = json.loads(receipt_path.read_text(encoding="utf-8"))
    retained["packet_sha256"] = "0" * 64
    receipt_path.write_text(
        json.dumps(retained, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rejects_root_replacement_during_recomputation(
    tmp_path, monkeypatch
):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    displaced_root = tmp_path / "displaced-receipt"
    original_preflight = freeze.preflight_annotator_submission

    def replace_visible_receipt(*args, **kwargs):
        receipt_root.rename(displaced_root)
        receipt_root.mkdir()
        (receipt_root / verify.RECEIPT_NAME).write_text("{}\n", encoding="utf-8")
        (receipt_root / "undeclared.txt").write_text("replacement\n", encoding="utf-8")
        return original_preflight(*args, **kwargs)

    monkeypatch.setattr(freeze, "preflight_annotator_submission", replace_visible_receipt)

    with pytest.raises(ValueError, match="changed during verification"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )


def test_receipt_verifier_rebinds_path_after_final_descriptor_read(
    tmp_path, monkeypatch
):
    receipt_root, submission, bundle = _published_receipt(tmp_path)
    receipt_path = receipt_root / verify.RECEIPT_NAME
    original_read = verify._read_descriptor_bytes
    reads = 0

    def replace_during_final_read(file_descriptor):
        nonlocal reads
        reads += 1
        content = original_read(file_descriptor)
        if reads == 2:
            receipt_path.unlink()
            receipt_path.write_text("{}\n", encoding="utf-8")
        return content

    monkeypatch.setattr(verify, "_read_descriptor_bytes", replace_during_final_read)

    with pytest.raises(ValueError, match="changed during verification"):
        verify.verify_preflight_receipt(
            receipt_root=receipt_root,
            rating_path=submission,
            annotator_bundle_root=bundle,
        )
