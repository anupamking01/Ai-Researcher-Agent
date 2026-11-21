"""No real ratings: enforce portable numeric JSON in blinded-freeze records."""

import pytest

from scripts import verify_human_eval_freeze as verifier


@pytest.mark.parametrize(
    "number",
    ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"],
)
def test_freeze_json_rejects_nonfinite_numeric_values(number):
    # Both freeze_manifest.json and agreement.json use this read boundary.
    raw = ('{"agreement": {"quadratic_weighted_cohen_kappa": ' + number + '}}').encode()
    with pytest.raises(ValueError, match="synthetic agreement contains a non-finite JSON number"):
        verifier._load_json_bytes(raw, label="synthetic agreement")


def test_freeze_json_accepts_finite_agreement_numbers():
    raw = b'{"agreement":{"kappa":-0.25,"raw_exact_agreement":1.0e0,"n":2}}'
    assert verifier._load_json_bytes(raw, label="synthetic agreement") == {
        "agreement": {"kappa": -0.25, "raw_exact_agreement": 1.0, "n": 2}
    }


def test_freeze_json_still_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="duplicate JSON key"):
        verifier._load_json_bytes(b'{"count":1,"count":2}', label="synthetic manifest")
