"""Synthetic tests: provenance must bind the bytes actually validated.

These fixtures are not human annotations or experimental results. Mutations
simulate an editor saving an input while a freeze is in progress, without
threads, sleeps, model calls, or nondeterministic timing.
"""
import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze


def _csv_bytes(*, score="2", notes="", newline="\r\n"):
    with io.StringIO(newline="") as stream:
        writer = csv.writer(stream, lineterminator=newline)
        writer.writerow(freeze.RATING_FIELDS)
        for annotator in ("synthetic-a", "synthetic-b"):
            writer.writerow([annotator, "H001", score, "3", "4", "4", "3", notes])
        return stream.getvalue().encode("utf-8")


@pytest.fixture
def inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_bytes(
        (json.dumps({"blind_id": "H001", "question": "Synthetic Q", "report_markdown": "Fixture"}) + "\n")
        .encode("utf-8")
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_bytes(b"# Synthetic protocol fixture\n")
    assignment = tmp_path / "assignment.md"
    assignment.write_bytes(b"# Synthetic assignment fixture\n")
    ratings = tmp_path / "ratings.csv"
    ratings.write_bytes(_csv_bytes())
    return ratings, {
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "freeze",
    }


def _frozen_rows(options):
    with (options["output_root"] / "frozen_ratings.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.mark.parametrize("replacement_notes", ["", "An editor saved a longer version."])
def test_rating_digest_and_scores_use_the_same_snapshot(inputs, monkeypatch, replacement_notes):
    ratings, options = inputs
    original = ratings.read_bytes()
    replacement = _csv_bytes(score="4", notes=replacement_notes)
    reader = csv.DictReader
    saves = []

    def save_before_parsing(handle, *args, **kwargs):
        if not saves:
            # In-place save after input capture but before CSV field parsing.
            # The original importer hashed the old bytes then read the new ones.
            ratings.write_bytes(replacement)
            saves.append(True)
        return reader(handle, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(freeze.csv, "DictReader", save_before_parsing)
        manifest = freeze.freeze_ratings([ratings], **options)

    assert saves == [True]
    assert ratings.read_bytes() == replacement
    assert manifest["rating_inputs"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["rating_inputs"][0]["bytes"] == len(original)
    assert [row["correctness_1_5"] for row in _frozen_rows(options)] == ["2", "2"]
    assert [row["notes"] for row in _frozen_rows(options)] == ["", ""]


@pytest.mark.parametrize("remove_after_validation", [False, True])
def test_packet_manifest_uses_validated_bytes_not_a_later_version(inputs, monkeypatch, remove_after_validation):
    ratings, options = inputs
    packet = options["packet_path"]
    original = packet.read_bytes()
    agreement = freeze.build_agreement

    def edit_after_validation(rows):
        if remove_after_validation:
            packet.unlink()
        else:
            packet.write_bytes(b'{"blind_id":"H999","question":"replacement"}\n')
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", edit_after_validation)
    manifest = freeze.freeze_ratings([ratings], **options)
    assert manifest["packet"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["packet"]["bytes"] == len(original)
    assert manifest["packet"]["n_blind_ids"] == 1
    assert {row["blind_id"] for row in _frozen_rows(options)} == {"H001"}


@pytest.mark.parametrize("option,entry", [
    ("protocol_path", "protocol"),
    ("assignment_plan_path", "assignment_plan"),
])
def test_plan_provenance_is_captured_before_processing_ratings(inputs, monkeypatch, option, entry):
    ratings, options = inputs
    path = options[option]
    original = path.read_bytes()
    agreement = freeze.build_agreement

    def edit_after_validation(rows):
        path.write_bytes(b"# Changed after rating validation\n")
        return agreement(rows)

    monkeypatch.setattr(freeze, "build_agreement", edit_after_validation)
    manifest = freeze.freeze_ratings([ratings], **options)
    assert manifest[entry]["sha256"] == hashlib.sha256(original).hexdigest()
    assert path.read_bytes() != original


@pytest.mark.parametrize("option", ["ratings", "packet_path"])
def test_data_input_is_opened_for_reading_once(inputs, monkeypatch, option):
    ratings, options = inputs
    watched = ratings if option == "ratings" else options[option]
    opened = []
    path_open = Path.open

    def count_reads(self, mode="r", *args, **kwargs):
        if self == watched and "r" in mode:
            opened.append(mode)
        return path_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", count_reads)
    freeze.freeze_ratings([ratings], **options)
    assert len(opened) == 1, opened


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
@pytest.mark.parametrize("notes", ["", 'Synthetic note, with "quotes"\r\nSecond line: caf\u00e9 / \u03bb.'])
def test_snapshot_preserves_raw_fingerprints_and_valid_csv_content(inputs, newline, notes):
    ratings, options = inputs
    original = _csv_bytes(notes=notes, newline=newline)
    ratings.write_bytes(original)
    packet = options["packet_path"].read_bytes()
    manifest = freeze.freeze_ratings([ratings], **options)
    assert ratings.read_bytes() == original
    assert manifest["rating_inputs"][0]["bytes"] == len(original)
    assert manifest["rating_inputs"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["packet"]["bytes"] == len(packet)
    assert manifest["packet"]["sha256"] == hashlib.sha256(packet).hexdigest()
    assert [row["notes"] for row in _frozen_rows(options)] == [notes, notes]


@pytest.mark.parametrize("option", ["ratings", "packet_path"])
def test_invalid_utf8_snapshot_cannot_publish_results(inputs, option):
    ratings, options = inputs
    path = ratings if option == "ratings" else options[option]
    path.write_bytes(b"\xff\xfeinvalid UTF-8")
    with pytest.raises(UnicodeDecodeError):
        freeze.freeze_ratings([ratings], **options)
    assert not options["output_root"].exists()
