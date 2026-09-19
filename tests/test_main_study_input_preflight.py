import pytest

from scripts.validate_main_study_inputs import validate_rows


def _main_row(**overrides):
    row = {
        "successful_sources": "3",
        "total_tokens": "1200",
        "treatment_cost_usd": "0.04",
        "latency_seconds": "12.5",
        "model_calls": "2",
        "report_words": "500",
    }
    row.update(overrides)
    return row


def _support_row(**overrides):
    row = {
        "claims_checked": "4",
        "supported": "2",
        "partially_supported": "1",
        "unsupported": "1",
        "contradicted": "0",
    }
    row.update(overrides)
    return row


def test_preflight_accepts_well_formed_rows():
    validate_rows([_main_row()], [_support_row()])


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-1"])
def test_preflight_rejects_invalid_measurements(value):
    with pytest.raises(ValueError):
        validate_rows([_main_row(latency_seconds=value)], [_support_row()])


@pytest.mark.parametrize("value", ["3.6", "nan", "inf", "-1"])
def test_preflight_rejects_malformed_scientific_counts(value):
    with pytest.raises(ValueError):
        validate_rows([_main_row()], [_support_row(supported=value)])


def test_preflight_rejects_nonconserving_evaluator_counts():
    with pytest.raises(ValueError, match="count mismatch"):
        validate_rows([_main_row()], [_support_row(supported="3")])


def test_preflight_requires_positive_claim_denominator():
    with pytest.raises(ValueError, match="must be positive"):
        validate_rows(
            [_main_row()],
            [_support_row(claims_checked="0", supported="0", partially_supported="0", unsupported="0")],
        )
