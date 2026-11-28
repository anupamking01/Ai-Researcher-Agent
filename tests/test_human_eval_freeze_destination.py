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
from scripts import verify_human_eval_freeze as verifier
from human_eval_test_support import write_valid_annotator_attestations


@pytest.fixture
def inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(
        json.dumps({"blind_id": "H001", "task_id": "main-01",
                    "question": "Synthetic question", "report_markdown": "Synthetic report"})
        + "\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_bytes(freeze.DEFAULT_PROTOCOL.read_bytes())
    assignment = tmp_path / "assignment.md"
    assignment.write_bytes(freeze.DEFAULT_ASSIGNMENT_PLAN.read_bytes())
    ratings = _ratings(tmp_path / "ratings.csv", "2")
    return ratings, {
        "annotator_attestations_path": write_valid_annotator_attestations(
            tmp_path / "annotator_attestations.csv",
            ("synthetic-a", "synthetic-b"),
        ),
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "frozen",
    }


def _ratings(path, score):
    """Create separate raw submissions so destination tests reach the write boundary."""
    paths = []
    for annotator in ("synthetic-a", "synthetic-b"):
        source = path.with_name(f"{path.stem}-{annotator}{path.suffix}")
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(freeze.RATING_FIELDS)
            writer.writerow([annotator, "H001", score, "3", "4", "4", "3", ""])
        paths.append(source)
    return paths


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
        freeze.freeze_ratings(ratings, **options)

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
            freeze.freeze_ratings(competing_ratings, **options)
        winner.update(_snapshot(options["output_root"]))
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", complete_other_attempt)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(ratings, **options)

    assert _snapshot(options["output_root"]) == winner
    assert winner


def test_directory_created_after_preflight_is_not_adopted(inputs, monkeypatch):
    ratings, options = inputs
    agreement = freeze.build_agreement
    reserved = False

    def reserve_elsewhere(rows):
        nonlocal reserved
        if not reserved:
            options["output_root"].mkdir()
            reserved = True
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", reserve_elsewhere)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(ratings, **options)
    assert list(options["output_root"].iterdir()) == []


def test_interleaved_second_attempt_can_win_atomic_publication(inputs, monkeypatch):
    ratings, options = inputs
    write_csv = freeze._write_csv
    competing_ratings = _ratings(ratings[0].with_name("interleaved.csv"), "4")
    winner = {}

    def interleaved_write(path, rows):
        with monkeypatch.context() as context:
            context.setattr(freeze, "_write_csv", write_csv)
            freeze.freeze_ratings(competing_ratings, **options)
        winner.update(_snapshot(options["output_root"]))
        write_csv(path, rows)

    monkeypatch.setattr(freeze, "_write_csv", interleaved_write)
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(ratings, **options)

    assert _snapshot(options["output_root"]) == winner
    assert winner


def test_failed_first_write_never_publishes_final_directory(inputs, monkeypatch):
    ratings, options = inputs

    def fail_write(path, rows):
        raise OSError("synthetic write failure")

    with monkeypatch.context() as context:
        context.setattr(freeze, "_write_csv", fail_write)
        with pytest.raises(OSError, match="synthetic write failure"):
            freeze.freeze_ratings(ratings, **options)

    assert not options["output_root"].exists()
    staging = list(options["output_root"].parent.glob(".frozen.staging-*"))
    assert len(staging) == 1
    assert staging[0].is_dir()


def test_staged_snapshot_is_verified_before_atomic_publication(inputs, monkeypatch):
    ratings, options = inputs
    real_verify = verifier.verify_frozen_snapshot
    observations = []

    def observe_verification(*args, **kwargs):
        freeze_root = Path(kwargs["freeze_root"])
        observations.append(
            {
                "final_exists": options["output_root"].exists(),
                "staging_name": freeze_root.name,
            }
        )
        return real_verify(*args, **kwargs)

    monkeypatch.setattr(verifier, "verify_frozen_snapshot", observe_verification)
    freeze.freeze_ratings(ratings, **options)

    assert len(observations) == 1
    assert observations[0]["final_exists"] is False
    assert observations[0]["staging_name"].startswith(".frozen.staging-")


def test_competing_destination_created_at_publish_is_preserved(
    inputs, monkeypatch
):
    ratings, options = inputs
    output = options["output_root"]
    staged = []

    def competing_publish(staging_root, destination):
        staged.append(Path(staging_root))
        destination.mkdir()
        (destination / "winner.txt").write_text("competing freeze", encoding="utf-8")
        raise ValueError(f"refusing to overwrite human-evaluation output: {destination}")

    monkeypatch.setattr(
        freeze, "_publish_directory_noreplace", competing_publish, raising=False
    )
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(ratings, **options)

    assert (output / "winner.txt").read_text(encoding="utf-8") == "competing freeze"
    assert len(staged) == 1
    assert staged[0].is_dir()


def test_staging_directory_replacement_is_detected_before_publish(
    inputs, monkeypatch
):
    ratings, options = inputs
    replacements = []

    def replace_staging(*args, **kwargs):
        staging = Path(kwargs["freeze_root"])
        detached = staging.with_name(f"{staging.name}-detached")
        staging.rename(detached)
        staging.mkdir()
        (staging / "owner.txt").write_text("replacement", encoding="utf-8")
        replacements.append((staging, detached))
        return {"status": "synthetic verifier result"}

    monkeypatch.setattr(verifier, "verify_frozen_snapshot", replace_staging)
    with pytest.raises(ValueError, match="staging root changed"):
        freeze.freeze_ratings(ratings, **options)

    assert not options["output_root"].exists()
    assert len(replacements) == 1
    replacement, detached = replacements[0]
    assert (replacement / "owner.txt").read_text(encoding="utf-8") == "replacement"
    assert (detached / "freeze_manifest.json").is_file()


def test_fresh_nested_destination_preserves_output_hashes(inputs):
    ratings, options = inputs
    options["output_root"] = options["output_root"] / "nested" / "v1"
    originals = [path.read_bytes() for path in ratings]
    manifest = freeze.freeze_ratings(ratings, **options)
    assert [path.read_bytes() for path in ratings] == originals
    assert len(manifest["rating_inputs"]) == len(originals)
    for source, original in zip(manifest["rating_inputs"], originals):
        assert source["sha256"] == hashlib.sha256(original).hexdigest()
        assert source["bytes"] == len(original)
    saved = _snapshot(options["output_root"])
    assert json.loads(saved["freeze_manifest.json"]) == manifest
    for entry in ("frozen_ratings", "agreement"):
        content = saved[manifest[entry]["path"]]
        assert manifest[entry]["bytes"] == len(content)
        assert manifest[entry]["sha256"] == hashlib.sha256(content).hexdigest()


def test_validation_failure_does_not_reserve_destination(inputs):
    ratings, options = inputs
    ratings = _ratings(ratings[0].with_name("invalid.csv"), "6")
    with pytest.raises(ValueError, match="outside the 1-5 rubric"):
        freeze.freeze_ratings(ratings, **options)
    assert not options["output_root"].exists()


def test_completed_snapshot_still_cannot_be_overwritten(inputs):
    ratings, options = inputs
    freeze.freeze_ratings(ratings, **options)
    saved = _snapshot(options["output_root"])
    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze.freeze_ratings(ratings, **options)
    assert _snapshot(options["output_root"]) == saved


def test_cli_refuses_existing_empty_destination_without_success(inputs):
    ratings, options = inputs
    options["output_root"].mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "scripts.freeze_human_eval_ratings", *map(str, ratings),
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
