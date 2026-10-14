"""Synthetic fail-closed contracts for standalone annotator-bundle distribution.

All files are synthetic; no treatment traces or real ratings are used.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from scripts import export_human_eval_annotator_bundle as exporter


def _write_bundle(root: Path, packet_rows: list[dict], *, template_ids=None, n_reports=None) -> Path:
    root.mkdir()
    packet_bytes = (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in packet_rows)
        + "\n"
    ).encode("utf-8")
    (root / "packet.jsonl").write_bytes(packet_bytes)

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(exporter.build.RATING_FIELDS))
    writer.writeheader()
    for blind_id in (template_ids if template_ids is not None else [row["blind_id"] for row in packet_rows]):
        writer.writerow({"blind_id": str(blind_id)})
    template_bytes = output.getvalue().encode("utf-8")
    (root / "ratings_template.csv").write_bytes(template_bytes)
    guide_bytes = exporter.DEFAULT_ANNOTATOR_GUIDE.read_bytes()
    (root / "annotator_instructions.md").write_bytes(guide_bytes)
    manifest = {
        "schema_version": 1,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
        "n_reports": len(packet_rows) if n_reports is None else n_reports,
        "content_validator_runtime": (
            exporter.build.content_validator_runtime_contract()
        ),
        "artifacts": {
            "packet": {"path": "packet.jsonl", **exporter._fingerprint(packet_bytes)},
            "ratings_template": {"path": "ratings_template.csv", **exporter._fingerprint(template_bytes)},
            "annotator_instructions": {
                "path": "annotator_instructions.md",
                **exporter._fingerprint(guide_bytes),
            },
        },
    }
    (root / "annotator_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root


def _rows():
    return [
        {"blind_id": "H001", "task_id": "main-01", "question": "Synthetic question?",
         "report_markdown": "# Synthetic report"},
        {"blind_id": "H002", "task_id": "main-02", "question": "Other synthetic question?",
         "report_markdown": "# Second synthetic report"},
    ]


def _rehash_packet(root: Path, packet_bytes: bytes) -> None:
    (root / "packet.jsonl").write_bytes(packet_bytes)
    manifest_path = root / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["packet"] = {
        "path": "packet.jsonl",
        **exporter._fingerprint(packet_bytes),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_standalone_bundle_accepts_valid_synthetic_packet(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    receipt = exporter.verify_annotator_bundle(root)
    assert receipt["n_reports"] == 2
    assert receipt["coordinator_artifacts_included"] is False
    assert receipt["annotator_guide_sha256"] == (
        exporter.FROZEN_ANNOTATOR_GUIDE_SHA256
    )


@pytest.mark.parametrize("duplicate_key", ["blind_id", r"bl\u0069nd_id"])
def test_standalone_bundle_rejects_duplicate_packet_keys_even_if_rehashed(
    tmp_path, duplicate_key
):
    root = _write_bundle(tmp_path / "bundle", _rows())
    packet_path = root / "packet.jsonl"
    lines = packet_path.read_text(encoding="utf-8").splitlines()
    lines[0] = '{"' + duplicate_key + '":"H999",' + lines[0][1:]
    _rehash_packet(root, ("\n".join(lines) + "\n").encode("utf-8"))

    with pytest.raises(ValueError, match="duplicate JSON key.*blind_id.*packet line 1"):
        exporter.verify_annotator_bundle(root)


@pytest.mark.parametrize("duplicate_key", ["status", r"st\u0061tus"])
def test_standalone_bundle_rejects_duplicate_manifest_keys(
    tmp_path, duplicate_key
):
    root = _write_bundle(tmp_path / "bundle", _rows())
    manifest_path = root / "annotator_manifest.json"
    original = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(
        '{"' + duplicate_key + '":"ambiguous",' + original[1:],
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate JSON key.*status.*annotator manifest"):
        exporter.verify_annotator_bundle(root)


def test_standalone_bundle_rejects_undeclared_manifest_fields(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    manifest_path = root / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["treatment_assignments"] = {"H001": "P6V"}
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="annotator manifest schema"):
        exporter.verify_annotator_bundle(root)


def test_standalone_bundle_rejects_modified_distribution_note(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    manifest_path = root / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["distribution_note"] = "H001 was produced by treatment P6V."
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="distribution_note"):
        exporter.verify_annotator_bundle(root)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("blind_id", 7),
        ("task_id", {"variant_id": "P6"}),
        ("question", {"variant_id": "D3"}),
        ("report_markdown", ["P6"]),
        ("question", ""),
        ("report_markdown", " "),
    ],
)
def test_standalone_bundle_rejects_nontext_or_empty_packet_fields(
    tmp_path, field, value
):
    rows = _rows()
    rows[0][field] = value
    root = _write_bundle(tmp_path / "bundle", rows)
    with pytest.raises(ValueError, match="packet.*(text|string)"):
        exporter.verify_annotator_bundle(root)


@pytest.mark.parametrize("n_reports", [0, 3, 2.0, True])
def test_standalone_bundle_rejects_incorrect_or_nonnumeric_report_count(
    tmp_path, n_reports
):
    root = _write_bundle(tmp_path / "bundle", _rows(), n_reports=n_reports)
    with pytest.raises(ValueError, match="n_reports"):
        exporter.verify_annotator_bundle(root)


def test_standalone_bundle_rejects_template_order_mismatch(tmp_path):
    rows = _rows()
    root = _write_bundle(
        tmp_path / "bundle", rows, template_ids=["H002", "H001"]
    )
    with pytest.raises(ValueError, match="order"):
        exporter.verify_annotator_bundle(root)
