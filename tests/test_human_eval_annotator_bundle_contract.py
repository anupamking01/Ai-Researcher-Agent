"""Synthetic fail-closed contracts for standalone annotator-bundle distribution.

All files are synthetic; no treatment traces or real ratings are used.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from scripts import export_human_eval_annotator_bundle as exporter


def test_default_output_name_tracks_manifest_schema():
    assert exporter.DEFAULT_OUTPUT_ROOT.name == "annotator-bundle-v2"


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
        "schema_version": 2,
        "study_id": "budget-main-v1",
        "status": "human_eval_annotator_distribution",
        "coordinator_artifacts_included": False,
        "presentation_order": "canonical",
        "n_reports": len(packet_rows) if n_reports is None else n_reports,
        "content_validator": exporter._content_validator_source_contract(),
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


def test_standalone_bundle_rejects_legacy_schema_without_order_contract(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    manifest_path = root / "annotator_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = 1
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="schema_version mismatch"):
        exporter.verify_annotator_bundle(root)


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


def test_window_custody_accepts_unchanged_synthetic_bundle(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    receipt = exporter.verify_annotator_bundle(root)
    assert receipt["status"] == "human_eval_annotator_distribution_verified"


def test_window_custody_rejects_same_byte_replacement_of_earlier_packet(
    tmp_path, monkeypatch
):
    root = _write_bundle(tmp_path / "bundle", _rows())
    target = root / "packet.jsonl"
    detached = tmp_path / "detached_packet.jsonl"
    original_reader = exporter._regular_bytes
    replaced = []

    def replace_after_packet_capture(path, *, label):
        content = original_reader(path, label=label)
        if label == "annotator ratings template" and not replaced:
            original = target.read_bytes()
            target.rename(detached)
            target.write_bytes(original)
            replaced.append(True)
        return content

    monkeypatch.setattr(exporter, "_regular_bytes", replace_after_packet_capture)
    with pytest.raises(ValueError, match="packet.jsonl changed during verification window|bundle root changed during verification window"):
        exporter.verify_annotator_bundle(root)
    assert replaced == [True]


def test_window_custody_rejects_late_in_place_instruction_change(
    tmp_path, monkeypatch
):
    root = _write_bundle(tmp_path / "bundle", _rows())
    original_reader = exporter._regular_bytes
    modified = []

    def alter_after_instruction_capture(path, *, label):
        content = original_reader(path, label=label)
        if label == "annotator instructions" and not modified:
            (root / "annotator_instructions.md").write_bytes(content + b"\nsynthetic change\n")
            modified.append(True)
        return content

    monkeypatch.setattr(exporter, "_regular_bytes", alter_after_instruction_capture)
    with pytest.raises(ValueError, match="annotator_instructions.md changed during verification window"):
        exporter.verify_annotator_bundle(root)
    assert modified == [True]


def test_window_custody_rejects_late_undeclared_artifact(tmp_path, monkeypatch):
    root = _write_bundle(tmp_path / "bundle", _rows())
    original_reader = exporter._regular_bytes
    introduced = []

    def introduce_after_instruction_capture(path, *, label):
        content = original_reader(path, label=label)
        if label == "annotator instructions" and not introduced:
            (root / "unexpected.txt").write_text("synthetic", encoding="utf-8")
            introduced.append(True)
        return content

    monkeypatch.setattr(exporter, "_regular_bytes", introduce_after_instruction_capture)
    with pytest.raises(ValueError, match="artifact set mismatch"):
        exporter.verify_annotator_bundle(root)
    assert introduced == [True]


def test_window_custody_rejects_same_byte_bundle_root_replacement(
    tmp_path, monkeypatch
):
    import shutil

    root = _write_bundle(tmp_path / "bundle", _rows())
    detached = tmp_path / "detached_bundle"
    original_reader = exporter._regular_bytes
    replaced = []

    def swap_root_after_instruction_capture(path, *, label):
        content = original_reader(path, label=label)
        if label == "annotator instructions" and not replaced:
            root.rename(detached)
            shutil.copytree(detached, root)
            replaced.append(True)
        return content

    monkeypatch.setattr(exporter, "_regular_bytes", swap_root_after_instruction_capture)
    with pytest.raises(ValueError, match="bundle root changed during verification window"):
        exporter.verify_annotator_bundle(root)
    assert replaced == [True]


def test_window_custody_rejects_late_template_mutation(tmp_path, monkeypatch):
    root = _write_bundle(tmp_path / "bundle", _rows())
    original_reader = exporter._regular_bytes
    modified = []

    def alter_after_manifest_capture(path, *, label):
        content = original_reader(path, label=label)
        if label == "annotator manifest" and not modified:
            (root / "ratings_template.csv").write_bytes(
                (root / "ratings_template.csv").read_bytes() + b"\n"
            )
            modified.append(True)
        return content

    monkeypatch.setattr(exporter, "_regular_bytes", alter_after_manifest_capture)
    with pytest.raises(ValueError, match="ratings_template.csv changed during verification window"):
        exporter.verify_annotator_bundle(root)
    assert modified == [True]



def test_independently_pinned_delivery_accepts_original_synthetic_bundle(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    pin = hashlib.sha256((root / "annotator_manifest.json").read_bytes()).hexdigest()
    receipt = exporter.verify_annotator_bundle(root, expected_manifest_sha256=pin)
    assert receipt["annotator_manifest_sha256"] == pin
    assert receipt["coordinator_artifacts_included"] is False


def test_independently_pinned_delivery_rejects_coherently_rehashed_report(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    original_pin = hashlib.sha256(
        (root / "annotator_manifest.json").read_bytes()
    ).hexdigest()
    modified = _rows()
    modified[0]["report_markdown"] += " Synthetic report substitution."
    packet = (chr(10).join(json.dumps(row, sort_keys=True) for row in modified) + chr(10)).encode()
    _rehash_packet(root, packet)
    # This local-only check cannot authenticate the original distribution.
    assert exporter.verify_annotator_bundle(root)["n_reports"] == 2
    with pytest.raises(ValueError, match="independently pinned"):
        exporter.verify_annotator_bundle(
            root, expected_manifest_sha256=original_pin
        )


def test_independently_pinned_delivery_rejects_wrong_valid_digest(tmp_path):
    root = _write_bundle(tmp_path / "bundle", _rows())
    with pytest.raises(ValueError, match="independently pinned"):
        exporter.verify_annotator_bundle(
            root, expected_manifest_sha256="0" * 64
        )


@pytest.mark.parametrize("invalid_pin", [
    "", "a" * 63, "A" * 64, "g" * 64, 123, b"a" * 64, True,
])
def test_independently_pinned_delivery_rejects_invalid_pins(tmp_path, invalid_pin):
    root = _write_bundle(tmp_path / "bundle", _rows())
    with pytest.raises(ValueError, match="64 lowercase hex digits"):
        exporter.verify_annotator_bundle(
            root, expected_manifest_sha256=invalid_pin
        )


def test_delivery_pin_cli_verify_only_passes(tmp_path, monkeypatch, capsys):
    import sys

    root = _write_bundle(tmp_path / "bundle", _rows())
    pin = hashlib.sha256((root / "annotator_manifest.json").read_bytes()).hexdigest()
    monkeypatch.setattr(sys, "argv", [
        "export_human_eval_annotator_bundle.py",
        "--output-root", str(root),
        "--verify-only", "--expected-manifest-sha256", pin,
    ])
    assert exporter.main() == 0
    assert "HUMAN EVAL ANNOTATOR EXPORT: PASS" in capsys.readouterr().out


def test_delivery_pin_cli_rejects_wrong_pin(tmp_path, monkeypatch):
    import sys

    root = _write_bundle(tmp_path / "bundle", _rows())
    monkeypatch.setattr(sys, "argv", [
        "export_human_eval_annotator_bundle.py",
        "--output-root", str(root),
        "--verify-only", "--expected-manifest-sha256", "0" * 64,
    ])
    with pytest.raises(SystemExit, match="independently pinned"):
        exporter.main()


def test_delivery_pin_cli_disallows_pin_during_unpinned_export(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, "argv", [
        "export_human_eval_annotator_bundle.py",
        "--output-root", str(tmp_path / "does-not-exist"),
        "--expected-manifest-sha256", "0" * 64,
    ])
    with pytest.raises(SystemExit, match="requires --verify-only"):
        exporter.main()
