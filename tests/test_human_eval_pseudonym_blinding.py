"""Synthetic-only controls for treatment-blind, non-contact rater pseudonyms.

No human annotations, real identities, treatment outputs, or experimental
measurements are used. This validates the existing protocol's ID boundary.
"""
import csv
import io
import json
from pathlib import Path

import pytest

from scripts import freeze_human_eval_ratings as freeze


def _rating_bytes(annotator_id):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(freeze.RATING_FIELDS)
    writer.writerow([annotator_id, "H001", "3", "3", "3", "3", "3", ""])
    return buffer.getvalue().encode("utf-8")


def _attestation_bytes(annotator_id):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=freeze.ANNOTATOR_ATTESTATION_FIELDS)
    writer.writeheader()
    writer.writerow({
        "annotator_id": annotator_id,
        **freeze._REQUIRED_ATTESTATION_VALUES,
    })
    return buffer.getvalue().encode("utf-8")


@pytest.mark.parametrize(
    "unsafe",
    [
        "rater-D3",
        "rater-Ｐ６Ｖ",
        "coordinator-variant_id",
        "source-blinding_key.csv",
        "rater@example.org",
        "rater＠example.org",
        "https://example.org/rater",
        "www.example.org/rater",
        "<span>rater</span>",
        "![rater](image.png)",
        "[rater](https://example.org/p6v)",
    ],
)
def test_blinded_rating_submission_rejects_leaking_pseudonyms(tmp_path, unsafe):
    path = tmp_path / "ratings.csv"
    raw = _rating_bytes(unsafe)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="annotator_id must"):
        freeze._load_ratings([path], allowed_blind_ids={"H001"})
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "unsafe",
    [
        "rater-D6",
        "rater-Ｐ６Ｖ",
        "rater-run_id",
        "researcher@example.org",
        "https://example.org/rater",
        "<b>rater</b>",
        "![image](image.png)",
    ],
)
def test_attestation_rejects_leaking_pseudonyms(tmp_path, unsafe):
    path = tmp_path / "attestations.csv"
    raw = _attestation_bytes(unsafe)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="annotator_id must"):
        freeze._load_annotator_attestations(path)
    assert path.read_bytes() == raw


def test_direct_agreement_helper_enforces_blinded_pseudonyms():
    rows = [
        {
            "annotator_id": id_,
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for id_ in ("rater-A", "rater-P6V")
    ]
    with pytest.raises(ValueError, match="annotator_id must remain treatment-blind"):
        freeze.build_agreement(rows)


def test_international_noncontact_pseudonym_remains_allowed(tmp_path):
    pseudonym = "évaluateur-甲"
    ratings = tmp_path / "ratings.csv"
    attestations = tmp_path / "attestations.csv"
    ratings.write_bytes(_rating_bytes(pseudonym))
    attestations.write_bytes(_attestation_bytes(pseudonym))
    rows, _ = freeze._load_ratings([ratings], allowed_blind_ids={"H001"})
    attest_rows, _, _ = freeze._load_annotator_attestations(attestations)
    assert rows[0]["annotator_id"] == pseudonym
    assert attest_rows[0]["annotator_id"] == pseudonym
    # A valid international pseudonym is accepted as part of a genuine
    # two-identity diagnostic. A lone identity no longer generates a
    # misleading successful inter-annotator agreement receipt.
    second = dict(rows[0], annotator_id="independent-rater")
    agreement = freeze.build_agreement([rows[0], second])
    assert agreement["n_annotators"] == 2
    assert len(agreement["pairwise"]) == 1

def test_direct_agreement_and_coverage_reject_spreadsheet_formula_pseudonym():
    rows = [
        {
            "annotator_id": '=HYPERLINK("https://example.invalid","rater")',
            "blind_id": "H001",
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        },
    ]
    with pytest.raises(ValueError, match="spreadsheet-active"):
        freeze.build_agreement(rows)
    with pytest.raises(ValueError, match="spreadsheet-active"):
        freeze._validate_assignment_coverage(rows, ["H001"])


def _synthetic_packet_bytes(blind_id):
    return (
        json.dumps(
            {
                "blind_id": blind_id,
                "task_id": "main-01",
                "question": "Synthetic research question",
                "report_markdown": "Synthetic report.",
            },
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


@pytest.mark.parametrize(
    "unsafe",
    [
        "P6V",
        "D3",
        "H001-P6V",
        "Ｈ００１",
        "H００１",
        "H001\u200b",
        "H001 ",
        "H01",
        "H000",
        "H0001",
        "=HYPERLINK(\"https://example.invalid\",\"H001\")",
    ],
)
def test_standalone_freeze_packet_rejects_unblinded_or_noncanonical_report_ids(unsafe):
    with pytest.raises(ValueError, match="generated opaque H001-H999"):
        freeze._packet_blind_ids(
            Path("synthetic-packet.jsonl"), content=_synthetic_packet_bytes(unsafe)
        )


@pytest.mark.parametrize("unsafe", ["D3", "H001-P6V", "H000", "H００１"])
def test_direct_agreement_rejects_unblinded_report_ids(unsafe):
    rows = [
        {
            "annotator_id": annotator,
            "blind_id": unsafe,
            **{field: "3" for field in freeze.SCORE_FIELDS},
            "notes": "",
        }
        for annotator in ("rater-a", "rater-b")
    ]
    with pytest.raises(ValueError, match="generated opaque H001-H999"):
        freeze.build_agreement(rows)


def test_ratings_import_rejects_unblinded_id_even_if_caller_whitelists_it(tmp_path):
    path = tmp_path / "synthetic-ratings.csv"
    path.write_bytes(_rating_bytes("rater-a").replace(b"H001", b"P6V"))
    with pytest.raises(ValueError, match="generated opaque H001-H999"):
        freeze._load_ratings([path], allowed_blind_ids={"P6V"})


def test_direct_assignment_coverage_rejects_treatment_coded_id():
    rows = [{"annotator_id": "rater-a", "blind_id": "D6"}]
    with pytest.raises(ValueError, match="generated opaque H001-H999"):
        freeze._validate_assignment_coverage(rows, ["D6"])


def test_standalone_opaque_ids_preserve_valid_sparse_blind_labels():
    payload = _synthetic_packet_bytes("H999")
    assert freeze._packet_blind_ids(Path("synthetic-packet.jsonl"), content=payload) == [
        "H999"
    ]
