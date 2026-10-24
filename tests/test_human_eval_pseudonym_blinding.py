"""Synthetic-only controls for treatment-blind, non-contact rater pseudonyms.

No human annotations, real identities, treatment outputs, or experimental
measurements are used. This validates the existing protocol's ID boundary.
"""
import csv
import io

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
    assert freeze.build_agreement(rows)["n_annotators"] == 1
