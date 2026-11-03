"""Synthetic-only regression checks for a common blinded packet JSONL envelope.

These tests do not create human ratings or authenticate historical treatment
evidence; they test source-byte interpretation across prospective handoffs.
"""
import json
from pathlib import Path

import pytest

from scripts import export_human_eval_annotator_bundle as exporter
from scripts import freeze_human_eval_ratings as freeze


def _canonical_packet() -> bytes:
    rows = [
        {
            "blind_id": "H001",
            "task_id": "main-01",
            "question": "Café research question?",
            "report_markdown": "Synthetic report one.",
        },
        {
            "blind_id": "H002",
            "task_id": "main-02",
            "question": "Second synthetic question?",
            "report_markdown": "Synthetic report two.",
        },
    ]
    return (
        "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        + "\n"
    ).encode("utf-8")


def _freeze_reader(content: bytes):
    return freeze._packet_blind_ids(Path("packet.jsonl"), content=content)


def _bundle_reader(content: bytes):
    return exporter._read_jsonl_packet(content)


@pytest.mark.parametrize(
    "reader",
    (_freeze_reader, _bundle_reader),
    ids=("ratings-freeze", "annotator-bundle"),
)
def test_canonical_unicode_packet_is_accepted_without_rewriting(reader):
    packet = _canonical_packet()
    rows_or_ids = reader(packet)
    if reader is _freeze_reader:
        assert rows_or_ids == ["H001", "H002"]
    else:
        assert [row["blind_id"] for row in rows_or_ids] == ["H001", "H002"]
        assert rows_or_ids[0]["question"] == "Café research question?"


def _blank_after_last_record(packet: bytes) -> bytes:
    return packet + b"\n"


def _blank_between_records(packet: bytes) -> bytes:
    return packet.replace(b"\n", b"\n \n", 1)


def _crlf(packet: bytes) -> bytes:
    return packet.replace(b"\n", b"\r\n")


def _no_final_lf(packet: bytes) -> bytes:
    return packet[:-1]


def _prefixed_whitespace(packet: bytes) -> bytes:
    return b" " + packet


def _noncanonical_spacing(packet: bytes) -> bytes:
    return packet.replace(b'": "', b'":"', 1)


def _escaped_unicode(packet: bytes) -> bytes:
    return packet.replace("Café".encode("utf-8"), b"Caf\\u00e9", 1)


def _invalid_utf8(packet: bytes) -> bytes:
    return packet.replace("Café".encode("utf-8"), b"\xff", 1)


@pytest.mark.parametrize(
    ("mutate", "error"),
    (
        (_blank_after_last_record, "blank physical record"),
        (_blank_between_records, "blank physical record"),
        (_crlf, "LF-terminated physical records"),
        (_no_final_lf, "LF-terminated physical records"),
        (_prefixed_whitespace, "not canonical generator JSON"),
        (_noncanonical_spacing, "not canonical generator JSON"),
        (_escaped_unicode, "not canonical generator JSON"),
        (_invalid_utf8, "not valid UTF-8"),
    ),
    ids=(
        "extra-physical-record", "blank-middle-record", "crlf",
        "missing-final-lf", "leading-whitespace", "alternate-spacing",
        "escaped-unicode", "invalid-utf8",
    ),
)
@pytest.mark.parametrize(
    "reader",
    (_freeze_reader, _bundle_reader),
    ids=("ratings-freeze", "annotator-bundle"),
)
def test_noncanonical_or_ambiguous_packet_rejected_by_both_readers(reader, mutate, error):
    with pytest.raises(ValueError, match=error):
        reader(mutate(_canonical_packet()))


def test_freeze_rejects_blank_packet_record_before_reading_ratings(tmp_path, monkeypatch):
    packet_path = tmp_path / "packet.jsonl"
    packet_path.write_bytes(_blank_after_last_record(_canonical_packet()))

    def unexpected_rating_access(*args, **kwargs):
        pytest.fail("ratings must not be read after packet record-boundary failure")

    monkeypatch.setattr(freeze, "_load_ratings", unexpected_rating_access)
    output_root = tmp_path / "frozen"
    with pytest.raises(ValueError, match="blank physical record"):
        freeze.freeze_ratings(
            [tmp_path / "not-read.csv"],
            annotator_attestations_path=tmp_path / "not-read-attestations.csv",
            packet_path=packet_path,
            output_root=output_root,
        )
    assert not output_root.exists()
