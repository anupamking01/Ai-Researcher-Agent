"""Synthetic-only regressions for one raw submission file per annotator.

These fixtures test ingestion and verification, not human independence or study
outcomes. No treatment mapping, evaluator, or model is used.
"""
import csv
import hashlib
import io
import json
import sys

import pytest

from scripts import freeze_human_eval_ratings as freeze
from scripts import verify_human_eval_freeze as verify


def _csv_bytes(annotators):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(freeze.RATING_FIELDS)
    for annotator in annotators:
        for blind_id in ("H001", "H002"):
            writer.writerow([annotator, blind_id, "2", "3", "4", "3", "2", ""])
    return stream.getvalue().encode("utf-8")


@pytest.fixture
def submission_inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text("".join(
        json.dumps({"blind_id": blind_id, "question": "Synthetic question",
                    "report_markdown": "Synthetic report"}) + "\n"
        for blind_id in ("H001", "H002")
    ), encoding="utf-8")
    protocol = tmp_path / "protocol.md"
    protocol.write_text("Synthetic protocol fixture\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("Synthetic assignment fixture\n", encoding="utf-8")
    paths = [tmp_path / "a.csv", tmp_path / "b.csv"]
    for path, annotator in zip(paths, ("synthetic-a", "synthetic-b")):
        path.write_bytes(_csv_bytes([annotator]))
    return paths, {
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "frozen",
    }


def _verify_options(options):
    return {"freeze_root" if key == "output_root" else key: value
            for key, value in options.items()}


@pytest.mark.parametrize("filename", ["combined.csv", "frozen_ratings.csv"])
def test_combined_submission_cannot_supply_two_independent_raters(submission_inputs, filename):
    paths, options = submission_inputs
    combined = paths[0].parent / filename
    original = _csv_bytes(["synthetic-a", "synthetic-b"])
    combined.write_bytes(original)
    # Four syntactically valid rows cover both items twice. The FILE identity,
    # not missing coverage, must reject this; even an output-like name is raw.
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        freeze.freeze_ratings([combined], **options)
    assert not options["output_root"].exists()
    assert combined.read_bytes() == original


@pytest.mark.parametrize("position", [0, 1, 2])
def test_header_only_submission_is_not_silently_accepted(submission_inputs, position):
    paths, options = submission_inputs
    empty = paths[0].parent / "empty.csv"
    empty.write_bytes(_csv_bytes([]))
    submitted = paths.copy()
    submitted.insert(position, empty)
    with pytest.raises(ValueError, match="no annotation rows"):
        freeze.freeze_ratings(submitted, **options)
    assert not options["output_root"].exists()


def test_separate_submissions_preserve_raw_bytes_and_combined_output(submission_inputs):
    paths, options = submission_inputs
    originals = [path.read_bytes() for path in paths]
    manifest = freeze.freeze_ratings(paths, **options)
    assert manifest["frozen_ratings"]["n_annotators"] == 2
    assert manifest["frozen_ratings"]["n_rows"] == 4
    for original, entry in zip(originals, manifest["rating_inputs"]):
        assert (options["output_root"] / entry["archive_path"]).read_bytes() == original
        assert entry["sha256"] == hashlib.sha256(original).hexdigest()
    # The normalized output legitimately contains both annotators. Verify it
    # from retained raw inputs and also with optional external source copies.
    for external in (None, paths):
        receipt = verify.verify_frozen_snapshot(external, **_verify_options(options))
        assert receipt["n_rows"] == 4
        assert receipt["n_annotators"] == 2
        assert receipt["blinding_key_used"] is False


@pytest.mark.parametrize("source_kind", ["archive", "legacy"])
def test_verifier_rejects_rehashed_combined_raw_input(submission_inputs, source_kind):
    paths, options = submission_inputs
    manifest = freeze.freeze_ratings(paths, **options)
    root = options["output_root"]
    # Preserve every normalized score and agreement output, but collapse the
    # two archived submissions into one and recompute its local fingerprint.
    combined = _csv_bytes(["synthetic-a", "synthetic-b"])
    first, second = manifest["rating_inputs"]
    (root / first["archive_path"]).write_bytes(combined)
    (root / second["archive_path"]).unlink()
    first.update(bytes=len(combined), sha256=hashlib.sha256(combined).hexdigest())
    manifest["rating_inputs"] = [first]
    external = None
    if source_kind == "legacy":
        first.pop("archive_path")
        paths[0].write_bytes(combined)
        external = [paths[0]]
    (root / "freeze_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        verify.verify_frozen_snapshot(external, **_verify_options(options))


def test_blank_annotator_id_remains_invalid(submission_inputs):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes([" "]))
    with pytest.raises(ValueError, match="missing annotator_id"):
        freeze.freeze_ratings(paths, **options)
    assert not options["output_root"].exists()


def test_freeze_cli_rejects_combined_submission_before_publication(submission_inputs, monkeypatch):
    paths, options = submission_inputs
    paths[0].write_bytes(_csv_bytes(["synthetic-a", "synthetic-b"]))
    monkeypatch.setattr(sys, "argv", [
        "freeze_human_eval_ratings", str(paths[0]),
        "--packet", str(options["packet_path"]),
        "--protocol", str(options["protocol_path"]),
        "--assignment-plan", str(options["assignment_plan_path"]),
        "--output-root", str(options["output_root"]),
    ])
    with pytest.raises(SystemExit, match="exactly one annotator_id"):
        freeze.main()
    assert not options["output_root"].exists()


def test_verifier_applies_identity_gate_to_optional_external_copy(submission_inputs):
    paths, options = submission_inputs
    freeze.freeze_ratings(paths, **options)
    paths[0].write_bytes(_csv_bytes(["synthetic-a", "synthetic-b"]))
    with pytest.raises(ValueError, match="exactly one annotator_id"):
        verify.verify_frozen_snapshot([paths[0]], **_verify_options(options))
