"""Synthetic-only checks for exclusive human-rating freeze destinations.

Interleavings are triggered at explicit boundaries, without timing or threads.
No scores here are human annotations or experimental findings.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze


@pytest.fixture
def inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(json.dumps({"blind_id": "H001"}) + "\n", encoding="utf-8")
    protocol = tmp_path / "protocol.md"
    protocol.write_text("# Synthetic protocol\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("# Synthetic assignment\n", encoding="utf-8")
    ratings = _ratings(tmp_path / "ratings.csv", "2")
    return ratings, {
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "frozen",
    }


def _ratings(path, score):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(freeze.RATING_FIELDS)
        for annotator in ("synthetic-a", "synthetic-b"):
            writer.writerow([annotator, "H001", score, "3", "4", "4", "3", ""])
    return path


def _snapshot(output):
    return {name: (output / name).read_bytes() for name in freeze.OUTPUT_FILES}


@pytest.mark.parametrize("kind", ["empty", "unrelated", "file", "symlink", "dangling"])
def test_existing_destination_is_never_adopted(inputs, tmp_path, kind):
    ratings, options = inputs
    output = options["output_root"]
    target = tmp_path / "target"
    if kind in {"empty", "unrelated"}:
        output.mkdir()
        if kind == "unrelated":
            (output / "keep.txt").write_bytes(b"unrelated user content")
    elif kind == "file":
        output.write_bytes(b"unrelated user content")
    else:
        if kind == "symlink":
            target.mkdir()
        output.symlink_to(target, target_is_directory=True)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings([ratings], **options)

    assert {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()} == before
    assert not any((output / name).exists() for name in freeze.OUTPUT_FILES)
    if kind in {"symlink", "dangling"}:
        assert output.is_symlink()
        assert target.exists() == (kind == "symlink")


def test_completed_competing_freeze_is_preserved(inputs, tmp_path, monkeypatch):
    ratings, options = inputs
    competing_ratings = _ratings(tmp_path / "competing.csv", "4")
    agreement = freeze.build_agreement
    winner = {}

    def complete_other_attempt(rows):
        with monkeypatch.context() as context:
            context.setattr(freeze, "build_agreement", agreement)
            freeze.freeze_ratings([competing_ratings], **options)
        winner.update(_snapshot(options["output_root"]))
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", complete_other_attempt)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings([ratings], **options)

    assert _snapshot(options["output_root"]) == winner
    assert winner


def test_directory_created_after_preflight_is_not_adopted(inputs, monkeypatch):
    ratings, options = inputs
    agreement = freeze.build_agreement

    def reserve_elsewhere(rows):
        options["output_root"].mkdir()
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", reserve_elsewhere)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings([ratings], **options)
    assert list(options["output_root"].iterdir()) == []


def test_second_attempt_is_rejected_before_first_output_write(inputs, monkeypatch):
    ratings, options = inputs
    write_csv = freeze._write_csv
    rejections = []

    def interleaved_write(path, rows):
        with monkeypatch.context() as context:
            context.setattr(freeze, "_write_csv", write_csv)
            with pytest.raises(ValueError, match="refusing to overwrite"):
                freeze.freeze_ratings([ratings], **options)
        rejections.append(True)
        write_csv(path, rows)

    monkeypatch.setattr(freeze, "_write_csv", interleaved_write)
    manifest = freeze.freeze_ratings([ratings], **options)
    assert rejections == [True]
    assert manifest["frozen_ratings"]["n_rows"] == 2


def test_failed_first_write_leaves_reserved_directory_and_no_success(inputs, monkeypatch):
    ratings, options = inputs

    def fail_write(path, rows):
        raise OSError("synthetic write failure")

    with monkeypatch.context() as context:
        context.setattr(freeze, "_write_csv", fail_write)
        with pytest.raises(OSError, match="synthetic write failure"):
            freeze.freeze_ratings([ratings], **options)

    assert options["output_root"].is_dir()
    assert list(options["output_root"].iterdir()) == []
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings([ratings], **options)


def test_fresh_nested_destination_preserves_output_hashes(inputs):
    ratings, options = inputs
    options["output_root"] = options["output_root"] / "nested" / "v1"
    original = ratings.read_bytes()
    manifest = freeze.freeze_ratings([ratings], **options)
    assert ratings.read_bytes() == original
    saved = _snapshot(options["output_root"])
    assert json.loads(saved["freeze_manifest.json"]) == manifest
    for entry in ("frozen_ratings", "agreement"):
        content = saved[manifest[entry]["path"]]
        assert manifest[entry]["bytes"] == len(content)
        assert manifest[entry]["sha256"] == hashlib.sha256(content).hexdigest()


def test_validation_failure_does_not_reserve_destination(inputs):
    ratings, options = inputs
    _ratings(ratings, "6")
    with pytest.raises(ValueError, match="outside the 1-5 rubric"):
        freeze.freeze_ratings([ratings], **options)
    assert not options["output_root"].exists()


def test_completed_snapshot_still_cannot_be_overwritten(inputs):
    ratings, options = inputs
    freeze.freeze_ratings([ratings], **options)
    saved = _snapshot(options["output_root"])
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings([ratings], **options)
    assert _snapshot(options["output_root"]) == saved


def test_cli_refuses_existing_empty_destination_without_success(inputs):
    ratings, options = inputs
    options["output_root"].mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "scripts.freeze_human_eval_ratings", str(ratings),
         "--packet", str(options["packet_path"]),
         "--protocol", str(options["protocol_path"]),
         "--assignment-plan", str(options["assignment_plan_path"]),
         "--output-root", str(options["output_root"])],
        cwd=Path(__file__).resolve().parents[1], capture_output=True,
        text=True, check=False, timeout=10,
    )
    assert result.returncode != 0
    assert "HUMAN EVAL FREEZE: FAIL" in result.stderr
    assert "Traceback" not in result.stderr
    assert "HUMAN EVAL FREEZE: PASS" not in result.stdout
    assert list(options["output_root"].iterdir()) == []
