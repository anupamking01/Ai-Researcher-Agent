"""Synthetic JSON-number integrity tests for reconciliation readiness.

These tests produce no human ratings and do not run study treatments.
"""

import pytest

from scripts import verify_human_reconciliation_readiness as readiness


@pytest.mark.parametrize(
    ("literal", "error"),
    [
        (b"NaN", "non-finite JSON numbers"),
        (b"Infinity", "non-finite JSON numbers"),
        (b"-Infinity", "non-finite JSON numbers"),
        (b"1e999", "non-finite JSON numbers"),
        (b"-1e999", "non-finite JSON numbers"),
        (b"9" * 129, "oversized JSON integer token"),
        (b"-" + b"9" * 129, "oversized JSON integer token"),
    ],
)
def test_reconciliation_readiness_rejects_nonfinite_or_oversized_numbers(
    literal, error
):
    # Put the malformed numeric leaf under an uninspected metadata key:
    # the strict decoder must reject it before downstream field selection.
    raw = b'{"schema_version":1,"metadata":{"value":' + literal + b"}}"
    with pytest.raises(ValueError, match=error):
        readiness._load(raw, "synthetic readiness receipt")


def test_nested_invalid_number_is_rejected_before_field_selection():
    with pytest.raises(ValueError, match="non-finite JSON numbers"):
        readiness._load(
            b'{"unused":[{"extra":{"value":NaN}}]}',
            "synthetic human analysis",
        )


def test_finite_json_numbers_and_literal_text_roundtrip():
    payload = readiness._load(
        b'{"small":-0.125,"large":1e308,"max_int":'
        + b"9" * 128
        + b',"blank":null,"flag":false,"literal":"Infinity NaN"}',
        "synthetic valid JSON",
    )
    assert payload["small"] == -0.125
    assert payload["large"] == 1e308
    assert len(str(payload["max_int"])) == 128
    assert payload["blank"] is None
    assert payload["flag"] is False
    assert payload["literal"] == "Infinity NaN"


def test_json_integer_digit_limit_exact_boundary():
    assert readiness._load(
        b'{"integer":-' + b"9" * 128 + b"}",
        "synthetic valid JSON",
    )["integer"] < 0


def test_direct_oversized_integer_fails_as_validation_error():
    with pytest.raises(ValueError, match="must be a finite number"):
        readiness._number(10 ** 400, "synthetic score")


def test_preserved_frozen_automated_analysis_remains_decodable():
    original = (readiness.ROOT / readiness.AUTO_JSON).read_bytes()
    payload = readiness._load(original, "frozen automated analysis")
    assert payload["study_id"] == readiness.STUDY
    assert set(payload["primary_contrasts"]) == set(readiness.CONTRASTS)
