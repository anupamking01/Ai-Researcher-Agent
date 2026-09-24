"""Synthetic fixtures for lossless CSV ingestion before human-rating freezes.

No values in this module are collected human ratings or study results.
"""
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.freeze_human_eval_ratings import RATING_FIELDS, freeze_ratings


@pytest.fixture
def inputs(tmp_path):
    packet = tmp_path / "packet.jsonl"
    packet.write_text(
        json.dumps({"blind_id": "H001", "question": "Synthetic fixture", "report_markdown": "Test"})
        + "\n",
        encoding="utf-8",
    )
    protocol = tmp_path / "protocol.md"
    protocol.write_text("# Synthetic protocol fixture\n", encoding="utf-8")
    assignment = tmp_path / "assignment.md"
    assignment.write_text("# Synthetic assignment fixture\n", encoding="utf-8")
    return {
        "packet_path": packet,
        "protocol_path": protocol,
        "assignment_plan_path": assignment,
        "output_root": tmp_path / "frozen",
    }


def _rows(notes=""):
    return [
        [annotator, "H001", "2", "3", "4", "4", "3", notes]
        for annotator in ("synthetic-a", "synthetic-b")
    ]


def _write(path, header, rows, *, lineterminator="\r\n"):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator=lineterminator)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _rejects_without_writes(ratings, inputs, match):
    before = ratings.read_bytes()
    with pytest.raises(ValueError, match=match):
        freeze_ratings([ratings], **inputs)
    assert ratings.read_bytes() == before
    assert not inputs["output_root"].exists()


@pytest.mark.parametrize("column", RATING_FIELDS)
def test_duplicate_header_cannot_overwrite_a_rating(tmp_path, inputs, column):
    header = [*RATING_FIELDS, column]
    rows = _rows("Synthetic note")
    for row in rows:
        # A duplicate score column previously replaced a valid original score.
        row.append("4" if column.endswith("_1_5") else row[RATING_FIELDS.index(column)])
    ratings = _write(tmp_path / "duplicate.csv", header, rows)
    _rejects_without_writes(ratings, inputs, "duplicate.*column")


@pytest.mark.parametrize("extra", ["silently discarded text", ""])
def test_extra_cells_cannot_be_silently_discarded(tmp_path, inputs, extra):
    rows = [row + [extra] for row in _rows()]
    ratings = _write(tmp_path / "extra.csv", RATING_FIELDS, rows)
    _rejects_without_writes(ratings, inputs, "extra.*field")


@pytest.mark.parametrize("last_column", ["notes", "clarity_1_5"])
def test_missing_cell_is_not_treated_as_explicitly_blank(tmp_path, inputs, last_column):
    header = [field for field in RATING_FIELDS if field != last_column] + [last_column]
    records = [dict(zip(RATING_FIELDS, row)) for row in _rows("Unable to assess clarity.")]
    rows = [[record[field] for field in header[:-1]] for record in records]
    ratings = _write(tmp_path / "short.csv", header, rows)
    _rejects_without_writes(ratings, inputs, "missing.*field")


def test_error_reports_physical_line_after_multiline_note(tmp_path, inputs):
    rows = _rows()
    rows[0][-1] = "First line, with comma\nSecond line"
    rows[1].append("unexpected")
    ratings = _write(tmp_path / "multiline.csv", RATING_FIELDS, rows)
    _rejects_without_writes(ratings, inputs, r"multiline\.csv:4:.*extra.*field")


def test_later_bad_file_does_not_publish_partial_snapshot(tmp_path, inputs):
    first = _write(tmp_path / "a.csv", RATING_FIELDS, _rows()[:1])
    second = _write(tmp_path / "b.csv", RATING_FIELDS, [_rows()[1] + ["extra"]])
    before = {path: path.read_bytes() for path in (first, second)}
    with pytest.raises(ValueError, match="extra.*field"):
        freeze_ratings([first, second], **inputs)
    assert all(path.read_bytes() == content for path, content in before.items())
    assert not inputs["output_root"].exists()


@pytest.mark.parametrize("lineterminator", ["\n", "\r\n"])
@pytest.mark.parametrize("reordered", [False, True])
def test_accepts_valid_quoted_multiline_unicode_notes(tmp_path, inputs, lineterminator, reordered):
    notes = 'Evidence, with "quotes"\nSecond line: caf\u00e9 and \u03bb.'
    header = list(reversed(RATING_FIELDS)) if reordered else list(RATING_FIELDS)
    records = [dict(zip(RATING_FIELDS, row)) for row in _rows(notes)]
    rows = [[record[field] for field in header] for record in records]
    ratings = _write(tmp_path / "valid.csv", header, rows, lineterminator=lineterminator)
    original = ratings.read_bytes()
    manifest = freeze_ratings([ratings], **inputs)
    assert ratings.read_bytes() == original
    assert manifest["rating_inputs"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert manifest["frozen_ratings"]["n_rows"] == 2
    with (inputs["output_root"] / "frozen_ratings.csv").open(encoding="utf-8", newline="") as handle:
        frozen = list(csv.DictReader(handle))
    assert [row["notes"] for row in frozen] == [notes, notes]
    assert [row["correctness_1_5"] for row in frozen] == ["2", "2"]


def test_accepts_explicit_blank_score_with_documented_reason(tmp_path, inputs):
    rows = _rows("Clarity cannot be assessed for this synthetic fixture.")
    for row in rows:
        row[RATING_FIELDS.index("clarity_1_5")] = ""
    ratings = _write(tmp_path / "blank_score.csv", RATING_FIELDS, rows)
    manifest = freeze_ratings([ratings], **inputs)
    assert manifest["frozen_ratings"]["dimension_counts"]["clarity_1_5"] == {"rated": 0, "missing": 2}


def test_accepts_explicit_empty_notes_cell(tmp_path, inputs):
    ratings = _write(tmp_path / "empty_notes.csv", RATING_FIELDS, _rows())
    manifest = freeze_ratings([ratings], **inputs)
    assert manifest["frozen_ratings"]["n_rows"] == 2


def test_cli_rejects_extra_cell_without_success_receipt(tmp_path, inputs):
    ratings = _write(tmp_path / "bad.csv", RATING_FIELDS, [row + ["extra"] for row in _rows()])
    result = subprocess.run(
        [
            sys.executable, "-m", "scripts.freeze_human_eval_ratings", str(ratings),
            "--packet", str(inputs["packet_path"]),
            "--protocol", str(inputs["protocol_path"]),
            "--assignment-plan", str(inputs["assignment_plan_path"]),
            "--output-root", str(inputs["output_root"]),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert "HUMAN EVAL FREEZE: FAIL" in result.stderr
    assert "extra" in result.stderr
    assert "Traceback" not in result.stderr
    assert not inputs["output_root"].exists()
