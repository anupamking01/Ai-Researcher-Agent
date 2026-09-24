import csv
import json
from pathlib import Path

import pytest

from scripts.freeze_human_eval_ratings import (
    RATING_FIELDS,
    SCORE_FIELDS,
    freeze_ratings,
    quadratic_weighted_kappa,
)


def _packet(tmp_path: Path) -> Path:
    packet = tmp_path / "packet.jsonl"
    rows = [
        {"blind_id": "H001", "task_id": "main-01", "question": "Q1", "report_markdown": "R1"},
        {"blind_id": "H002", "task_id": "main-02", "question": "Q2", "report_markdown": "R2"},
    ]
    packet.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    return packet


def _protocol(tmp_path: Path) -> Path:
    protocol = tmp_path / "HUMAN_EVAL_PROTOCOL.md"
    protocol.write_text("# Frozen protocol\n", encoding="utf-8")
    return protocol


def _ratings(tmp_path: Path, name: str, rows: list[dict], *, extra_fields: tuple[str, ...] = ()) -> Path:
    path = tmp_path / name
    fieldnames = list(RATING_FIELDS) + list(extra_fields)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(annotator: str, blind_id: str, scores=(4, 4, 4, 4, 4), notes="") -> dict:
    row = {
        "annotator_id": annotator,
        "blind_id": blind_id,
        "notes": notes,
    }
    row.update({field: str(score) if score is not None else "" for field, score in zip(SCORE_FIELDS, scores)})
    return row


def test_freeze_writes_blinded_snapshot_and_two_rater_agreement(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    first = _ratings(
        tmp_path,
        "annotator-a.csv",
        [
            _row("ann-a", "H001", (1, 2, 3, 4, 5), notes="Endpoint scores justified."),
            _row("ann-a", "H002", (2, 3, 4, 4, 3)),
        ],
    )
    second = _ratings(
        tmp_path,
        "annotator-b.csv",
        [
            _row("ann-b", "H001", (1, 2, 3, 4, 5), notes="Endpoint scores justified."),
            _row("ann-b", "H002", (2, 3, 4, 4, 3)),
        ],
    )
    output = tmp_path / "frozen-v1"

    manifest = freeze_ratings(
        [first, second],
        packet_path=packet,
        protocol_path=protocol,
        output_root=output,
    )

    assert manifest["status"] == "blinded_human_ratings_frozen"
    assert manifest["blinding_key_used"] is False
    assert manifest["frozen_ratings"]["n_rows"] == 4
    assert manifest["frozen_ratings"]["n_annotators"] == 2
    assert manifest["frozen_ratings"]["n_unique_blind_ids_rated"] == 2
    assert manifest["assignment_plan"]["path"] == "paper/HUMAN_EVAL_ASSIGNMENT_PLAN.md"
    assert manifest["assignment_coverage"]["required_min_raters_per_item"] == 2
    assert manifest["assignment_coverage"]["min_observed_raters_per_item"] == 2
    assert manifest["assignment_coverage"]["items_by_rater_count"] == {"2": 2}

    agreement = json.loads((output / "agreement.json").read_text(encoding="utf-8"))
    assert agreement["n_annotators"] == 2
    assert agreement["requires_predeclared_multi_rater_statistic"] is False
    correctness = agreement["pairwise"][0]["dimensions"]["correctness_1_5"]
    assert correctness["n_double_rated"] == 2
    assert correctness["raw_exact_agreement"] == 1.0
    assert correctness["quadratic_weighted_cohen_kappa"] == 1.0

    frozen_text = (output / "frozen_ratings.csv").read_text(encoding="utf-8")
    manifest_text = (output / "freeze_manifest.json").read_text(encoding="utf-8")
    assert "variant_id" not in frozen_text
    assert "variant_id" not in manifest_text
    assert "D3" not in frozen_text
    assert "P6V" not in manifest_text


def test_missing_dimension_requires_reason_in_notes(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    ratings = _ratings(
        tmp_path,
        "ratings.csv",
        [_row("ann-a", "H001", (4, None, 4, 4, 4), notes="")],
    )

    with pytest.raises(ValueError, match="unscored dimension without a reason"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


def test_endpoint_score_requires_note(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    ratings = _ratings(
        tmp_path,
        "ratings.csv",
        [_row("ann-a", "H001", (5, 4, 4, 4, 4), notes="")],
    )

    with pytest.raises(ValueError, match="endpoint score"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


@pytest.mark.parametrize("bad_score", ["0", "6", "3.5", "bad"])
def test_invalid_score_fails_closed(tmp_path: Path, bad_score: str):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    row = _row("ann-a", "H001")
    row["correctness_1_5"] = bad_score
    ratings = _ratings(tmp_path, "ratings.csv", [row])

    with pytest.raises(ValueError, match="1-5|integer"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


def test_unknown_blind_id_fails_closed(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    ratings = _ratings(tmp_path, "ratings.csv", [_row("ann-a", "H999")])

    with pytest.raises(ValueError, match="unknown blind_id"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


def test_duplicate_annotator_item_across_files_fails_closed(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    first = _ratings(tmp_path, "a.csv", [_row("ann-a", "H001")])
    second = _ratings(tmp_path, "b.csv", [_row("ann-a", "H001")])

    with pytest.raises(ValueError, match="duplicate independent rating"):
        freeze_ratings(
            [first, second],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


def test_treatment_identity_columns_are_rejected(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    row = _row("ann-a", "H001")
    row["variant_id"] = "D3"
    ratings = _ratings(
        tmp_path,
        "ratings.csv",
        [row],
        extra_fields=("variant_id",),
    )

    with pytest.raises(ValueError, match="must stay blinded"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )


def test_existing_snapshot_is_never_overwritten(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    ratings = _ratings(tmp_path, "ratings.csv", [_row("ann-a", "H001")])
    output = tmp_path / "freeze"
    output.mkdir()
    (output / "freeze_manifest.json").write_text('{"old": true}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to overwrite"):
        freeze_ratings(
            [ratings],
            packet_path=packet,
            protocol_path=protocol,
            output_root=output,
        )


def test_quadratic_weighted_kappa_is_undefined_for_single_constant_category():
    assert quadratic_weighted_kappa([(3, 3), (3, 3)]) is None


def test_freeze_fails_closed_until_every_packet_item_is_double_rated(tmp_path: Path):
    packet = _packet(tmp_path)
    protocol = _protocol(tmp_path)
    first = _ratings(
        tmp_path,
        "annotator-a.csv",
        [_row("ann-a", "H001"), _row("ann-a", "H002")],
    )
    second = _ratings(
        tmp_path,
        "annotator-b.csv",
        [_row("ann-b", "H001")],
    )

    with pytest.raises(ValueError, match="assignment incomplete"):
        freeze_ratings(
            [first, second],
            packet_path=packet,
            protocol_path=protocol,
            output_root=tmp_path / "freeze",
        )
