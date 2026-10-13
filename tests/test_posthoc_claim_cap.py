import json

import pytest

from scripts import evaluate_posthoc_support


def _cached_evaluation(**overrides):
    payload = {
        "max_claims": 12,
        "claims_checked": 12,
        "supported": 8,
        "partially_supported": 2,
        "unsupported": 1,
        "contradicted": 1,
        "examples": [],
    }
    payload.update(overrides)
    return payload


def test_posthoc_normalizer_enforces_frozen_claim_cap():
    raw = json.dumps(
        _cached_evaluation(
            claims_checked=13,
            supported=9,
        )
    )

    with pytest.raises(ValueError, match="exceeds max_claims=12"):
        evaluate_posthoc_support._normalize_evaluator_output(raw)


def test_cached_posthoc_evaluation_rejects_claims_above_cap(tmp_path):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(
            _cached_evaluation(
                claims_checked=13,
                supported=9,
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="exceeds max_claims=12"):
        evaluate_posthoc_support._load_cached_evaluation(path)


@pytest.mark.parametrize("declared_cap", [None, True, 11, 13, "12"])
def test_cached_posthoc_evaluation_requires_frozen_cap_metadata(
    tmp_path, declared_cap
):
    path = tmp_path / "cached.json"
    path.write_text(
        json.dumps(_cached_evaluation(max_claims=declared_cap)),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="max_claims metadata must equal 12"):
        evaluate_posthoc_support._load_cached_evaluation(path)


def test_cached_posthoc_evaluation_accepts_valid_record(tmp_path):
    expected = _cached_evaluation()
    path = tmp_path / "cached.json"
    path.write_text(json.dumps(expected), encoding="utf-8")

    assert evaluate_posthoc_support._load_cached_evaluation(path) == expected
