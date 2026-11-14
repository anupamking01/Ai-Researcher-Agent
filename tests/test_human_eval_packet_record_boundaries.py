"""Synthetic regression checks for blinded packet physical-record accounting.

No historical treatment reports or genuine human ratings are used here.
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


def _multiple_blank_records(packet: bytes) -> bytes:
    return packet + b"\n \n"


@pytest.mark.parametrize(
    "mutate",
    (_blank_after_last_record, _blank_between_records, _multiple_blank_records),
    ids=("extra-terminal-record", "blank-middle-record", "multiple-blank-records"),
)
@pytest.mark.parametrize(
    "reader",
    (_freeze_reader, _bundle_reader),
    ids=("ratings-freeze", "annotator-bundle"),
)
def test_unaccounted_blank_packet_record_rejected_by_both_readers(reader, mutate):
    with pytest.raises(ValueError, match="blank physical record"):
        reader(mutate(_canonical_packet()))


@pytest.mark.parametrize(
    "reader",
    (_freeze_reader, _bundle_reader),
    ids=("ratings-freeze", "annotator-bundle"),
)
def test_legacy_packet_format_still_parses_without_mutating_source_bytes(reader):
    packet = _canonical_packet()
    # Noncanonical serialization and CRLF are allowed by these standalone
    # readers; the source-bound coordinator verifier remains stricter.
    legacy_bytes = (
        packet.replace("Café".encode("utf-8"), b"Caf\\u00e9")
        .replace(b'": "', b'":"', 1)
        .replace(b"\n", b"\r\n")
    )
    assert reader(legacy_bytes)
    assert reader(legacy_bytes[:-2])  # Historical packet without final CRLF.


@pytest.mark.parametrize(
    "reader",
    (_freeze_reader, _bundle_reader),
    ids=("ratings-freeze", "annotator-bundle"),
)
def test_invalid_utf8_packet_is_rejected(reader):
    packet = _canonical_packet().replace("Café".encode("utf-8"), b"\xff", 1)
    if reader is _freeze_reader:
        # The freezer's existing API propagates Python's decoder exception.
        with pytest.raises(UnicodeDecodeError):
            reader(packet)
    else:
        with pytest.raises(ValueError, match="not valid UTF-8"):
            reader(packet)


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
